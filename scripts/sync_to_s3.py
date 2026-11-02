"""
Upload the SAT data folder from OneDrive to an S3 bucket.

The folder is located the same way the dashboard locates it (see
scripts/loaders/onedrive_path.py), so nothing machine-specific is stored
here. Each file keeps its path relative to that folder, under an optional
key prefix:

    <SAT root>/Foodservice/June_2026.xlsx
        -> s3://<bucket>/<prefix>/Foodservice/June_2026.xlsx

A file already in the bucket is uploaded again only when its size or its
modification time differs from the copy that is there, so a re-run costs one
HEAD request per unchanged file rather than a full upload.

The defaults target the existing QA bucket, so no argument is needed:

    python -m scripts.sync_to_s3 --dry-run
    python -m scripts.sync_to_s3

    -> s3://adhoc-qa-reports/SAT_Reports/SAT_DASHBOARD_REPORT/...

Override either half with --bucket / --prefix.

Credentials are read from the environment, never from this file. The
git-ignored .env in the project root is loaded automatically:

    AWS_ACCESS_KEY_ID=<your access key id>
    AWS_SECRET_ACCESS_KEY=<your secret access key>
    AWS_DEFAULT_REGION=<your bucket region, e.g. ap-southeast-1>

A shell variable, an ~/.aws profile or an EC2 instance role is used instead
when .env carries no keys.
"""

import argparse
import mimetypes
import sys
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError

# So the script runs both as `python -m scripts.sync_to_s3` and as
# `python scripts/sync_to_s3.py`, which puts scripts/ on the path, not the
# project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.loaders.onedrive_path import describe_search, resolve_sat_root  # noqa: E402

from scripts.loaders.s3_client import (  # noqa: E402
    AWS_REGION,
    DOTENV_PATH,
    S3_BUCKET,
    S3_PREFIX,
    get_client,
)


# The reports only. A .tmp or ~$lock file left by Excel is not data, and
# OneDrive keeps its own metadata files beside the reports.
SUFFIXES = {".xlsx", ".xls", ".xlsm", ".csv"}

# The local modification time is stored on the object, so an unchanged file
# can be recognised without downloading or hashing it.
MTIME_KEY = "source-mtime"


def _client():
    """The shared S3 client, with a missing credential reported as an exit."""

    try:
        return get_client()
    except RuntimeError as error:
        raise SystemExit(str(error))


def _files(root):
    """Every report under `root`, deepest path last, temporary files dropped."""

    for path in sorted(root.rglob("*")):

        if not path.is_file():
            continue

        if path.suffix.lower() not in SUFFIXES:
            continue

        # Excel writes "~$Report.xlsx" while a workbook is open.
        if path.name.startswith("~$") or path.name.startswith("."):
            continue

        yield path


def _key(path, root, prefix):
    """The object key: the path relative to the SAT root, under the prefix."""

    relative = path.relative_to(root).as_posix()

    return f"{prefix.strip('/')}/{relative}" if prefix else relative


def _unchanged(client, bucket, key, path):
    """
    True when the object already matches the local file.

    A missing object, or one written before this script stored the source
    mtime, counts as changed - re-uploading once is cheaper than reasoning
    about an object of unknown provenance.
    """

    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if error.response["Error"]["Code"] in ("404", "NoSuchKey", "403"):
            return False
        raise

    stat = path.stat()

    if head["ContentLength"] != stat.st_size:
        return False

    stored = head.get("Metadata", {}).get(MTIME_KEY)

    return stored == f"{int(stat.st_mtime)}"


def _ensure_folder(client, bucket, prefix):
    """
    Put the empty marker object the S3 console reads as a folder.

    S3 has no folders - a key containing "/" is enough for the upload to
    work. The marker only makes SAT_DASHBOARD_REPORT visible in the console
    when it is still empty, so a missing one is not an error.
    """

    if not prefix:
        return

    marker = prefix.strip("/") + "/"

    try:
        client.head_object(Bucket=bucket, Key=marker)
    except ClientError:
        try:
            client.put_object(Bucket=bucket, Key=marker, Body=b"")
            print(f"  created       {marker}")
        except ClientError as error:
            print(f"  folder marker not written ({error}); uploading anyway")


def _upload(client, bucket, key, path):
    """Upload one file, carrying its mtime and content type onto the object."""

    content_type = mimetypes.guess_type(path.name)[0]

    extra = {"Metadata": {MTIME_KEY: f"{int(path.stat().st_mtime)}"}}

    if content_type:
        extra["ContentType"] = content_type

    # upload_file handles the multipart split for a large workbook itself.
    client.upload_file(str(path), bucket, key, ExtraArgs=extra)


def sync(bucket, prefix, dry_run=False, force=False):
    """Walk the SAT folder and upload what the bucket does not already hold."""

    root = resolve_sat_root()

    if root is None:
        print("The SAT data folder could not be found.\n")
        print(describe_search())
        return 1

    target = f"s3://{bucket}/{prefix.strip('/')}" if prefix else f"s3://{bucket}"

    print(f"Source : {root}")
    print(f"Target : {target}")
    print(f"Region : {AWS_REGION}")

    if dry_run:
        print("Mode   : dry run, nothing is uploaded")

    print()

    if dry_run:
        client = None
    else:
        client = _client()
        _ensure_folder(client, bucket, prefix)

    uploaded = skipped = failed = 0

    for path in _files(root):

        key = _key(path, root, prefix)

        if dry_run:
            print(f"  would upload  {key}")
            uploaded += 1
            continue

        try:
            if not force and _unchanged(client, bucket, key, path):
                skipped += 1
                continue

            _upload(client, bucket, key, path)
            uploaded += 1
            print(f"  uploaded      {key}")

        except (BotoCoreError, ClientError, OSError) as error:
            failed += 1
            print(f"  FAILED        {key}: {error}")

    print(
        f"\n{uploaded} uploaded, {skipped} unchanged, {failed} failed."
    )

    return 1 if failed else 0


def main(argv=None):

    parser = argparse.ArgumentParser(
        description="Upload the SAT OneDrive folder to an S3 bucket."
    )
    parser.add_argument(
        "--bucket",
        default=S3_BUCKET,
        help="Target bucket (default: $SAT_S3_BUCKET).",
    )
    parser.add_argument(
        "--prefix",
        default=S3_PREFIX,
        help="Key prefix inside the bucket (default: $SAT_S3_PREFIX).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be uploaded without contacting AWS.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Upload every file, even one the bucket already matches.",
    )

    args = parser.parse_args(argv)

    return sync(args.bucket, args.prefix, args.dry_run, args.force)


if __name__ == "__main__":
    # python -m scripts.sync_to_s3 --dry-run

    sys.exit(main())
