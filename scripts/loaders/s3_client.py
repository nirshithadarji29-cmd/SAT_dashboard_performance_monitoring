"""
One place that knows how to reach the S3 bucket.

Both the uploader (scripts/sync_to_s3.py) and the dashboard's reader
(scripts/loaders/read_s3.py) build their client here, so the bucket, the
prefix and the credential rules are defined once instead of drifting apart.

No key is ever stored in this file. Values come from the environment, and
the git-ignored .env in the project root is loaded into the environment on
import:

    AWS_ACCESS_KEY_ID=<your access key id>
    AWS_SECRET_ACCESS_KEY=<your secret access key>
    AWS_DEFAULT_REGION=<your bucket region, e.g. ap-southeast-1>

A shell variable, an ~/.aws profile or an EC2 instance role is used instead
when .env carries no keys.
"""

import os
from pathlib import Path

import boto3

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOTENV_PATH = PROJECT_ROOT / ".env"


def load_dotenv(path=DOTENV_PATH):
    """
    Read KEY=value lines from .env into the environment.

    A value already set in the real environment wins, so a shell variable or
    a CI secret is never overwritten by the file.
    """

    if not path.is_file():
        return

    for line in path.read_text(encoding="utf-8-sig").splitlines():

        line = line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()

        # Quotes are how a value with spaces is written in .env; they are
        # not part of the value itself.
        value = value.strip().strip("\"'")

        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "<YOUR_AWS_ACCESS_KEY_ID>")
AWS_SECRET_ACCESS_KEY = os.getenv(
    "AWS_SECRET_ACCESS_KEY", "<YOUR_AWS_SECRET_ACCESS_KEY>"
)
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN")  # only for temporary keys
AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "ap-southeast-1")

# The bucket holds other QA output too, so the reports live under their own
# prefix: s3://adhoc-qa-reports/SAT_Reports/SAT_DASHBOARD_REPORT/...
S3_BUCKET = os.getenv("SAT_S3_BUCKET", "adhoc-qa-reports")
S3_PREFIX = os.getenv("SAT_S3_PREFIX", "SAT_Reports/SAT_DASHBOARD_REPORT")

PLACEHOLDER = "<YOUR_"


def s3_uri(bucket=None, prefix=None):
    """The configured location, as it is written in the AWS console."""

    bucket = S3_BUCKET if bucket is None else bucket
    prefix = S3_PREFIX if prefix is None else prefix

    return f"s3://{bucket}/{prefix.strip('/')}" if prefix else f"s3://{bucket}"


def get_client():
    """
    An S3 client.

    Explicit keys are passed only when .env or the shell actually supplied
    them. Otherwise the session is built with none, which leaves boto3 to
    its own chain - ~/.aws/credentials, an SSO profile, or the instance role
    when this runs on EC2 - rather than failing on a machine that is already
    authenticated another way.
    """

    keys_given = (
        PLACEHOLDER not in AWS_ACCESS_KEY_ID
        and PLACEHOLDER not in AWS_SECRET_ACCESS_KEY
    )

    if keys_given:
        session = boto3.session.Session(
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            aws_session_token=AWS_SESSION_TOKEN,
            region_name=AWS_REGION,
        )
    else:
        session = boto3.session.Session(region_name=AWS_REGION)

    if session.get_credentials() is None:
        raise RuntimeError(credentials_help())

    return session.client("s3")


def credentials_help():
    """What to set, shown wherever missing credentials surface."""

    return (
        f"No AWS credentials found.\n\n"
        f"Put them in {DOTENV_PATH} as\n"
        "  AWS_ACCESS_KEY_ID=<your access key id>\n"
        "  AWS_SECRET_ACCESS_KEY=<your secret access key>\n"
        "  AWS_DEFAULT_REGION=<your bucket region>\n\n"
        "or run `aws configure` to set up a profile."
    )
