"""
Read the monthly SAT reports from S3 instead of the OneDrive sync folder.

This is a drop-in replacement for scripts/loaders/read_onedrive.py: the same
four names (get_sat_root, load_all_data, refresh_data,
describe_data_problem) with the same meaning, so app.py only swaps its
import. The reports are uploaded by scripts/sync_to_s3.py and keep the
layout the OneDrive folder had:

    s3://<bucket>/<prefix>/<source>/<month>/*.xlsx

Everything after the read - business unit, lens, the Source / Month /
File_Name columns - is the OneDrive loader's own code, imported rather than
copied, so both paths shape a row identically.
"""

import io

import pandas as pd
import streamlit as st
from botocore.exceptions import BotoCoreError, ClientError

from config.settings import DATA_CACHE_TTL
from scripts.loaders.read_onedrive import _business_unit, _lens, classify_report
from scripts.loaders.s3_client import S3_BUCKET, S3_PREFIX, get_client, s3_uri

# Excel lock files and the zero-byte key that makes the prefix show up as a
# folder in the console are keys, not reports.
SUFFIX = ".xlsx"


@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner=False)
def get_sat_root():
    """
    The S3 location the reports are read from, as a display string.

    The OneDrive loader returned a Path here. Nothing downstream does path
    arithmetic on it - app.py prints it and passes it to load_all_data as a
    cache key - so the s3:// URI serves both purposes unchanged.
    """

    return s3_uri()


def refresh_data():
    """Invalidate every data cache so the next run re-reads from S3."""

    get_sat_root.clear()
    load_all_data.clear()


def _keys(client, bucket, prefix):
    """
    Every report key under the prefix, oldest path first.

    Paginated: list_objects_v2 returns at most 1000 keys per call, and a
    year of reports across several sources passes that quickly.
    """

    keys = []

    paginator = client.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix.strip("/")):

        for item in page.get("Contents", []):

            key = item["Key"]
            name = key.rsplit("/", 1)[-1]

            # The folder marker is a key ending in "/" with no name.
            if not name or name.startswith("~$"):
                continue

            if not name.lower().endswith(SUFFIX):
                continue

            keys.append(key)

    return sorted(keys)


def _source_and_month(key, prefix):
    """
    The <source> and <month> folders a key sits in.

    Mirrors the OneDrive walk, which took them from the two directory levels
    above the file. A key that is not nested that deep - a report dropped at
    the top of the prefix by hand - reports "Unknown" rather than being
    skipped, so it still appears in the data.
    """

    relative = key[len(prefix.strip("/")):].strip("/") if prefix else key

    parts = relative.split("/")

    if len(parts) >= 3:
        return parts[0], parts[1]

    if len(parts) == 2:
        return parts[0], "Unknown"

    return "Unknown", "Unknown"


def describe_data_problem(sat_root):
    """
    Explain why no data could be read from `sat_root`.

    Called from the error path in the UI, so it makes its own listing rather
    than relying on anything the failed load left behind.
    """

    try:
        client = get_client()
    except RuntimeError as error:
        return str(error)

    try:
        keys = _keys(client, S3_BUCKET, S3_PREFIX)
    except ClientError as error:
        code = error.response["Error"]["Code"]

        if code in ("NoSuchBucket",):
            return (
                f"The bucket '{S3_BUCKET}' does not exist in this account, "
                f"or is not visible to these credentials."
            )

        if code in ("AccessDenied", "403", "InvalidAccessKeyId",
                    "SignatureDoesNotMatch"):
            return (
                f"These credentials cannot list {sat_root}.\n\n"
                "The key needs s3:ListBucket on the bucket and s3:GetObject "
                "on the prefix."
            )

        if code in ("PermanentRedirect", "IllegalLocationConstraintException",
                    "AuthorizationHeaderMalformed"):
            return (
                f"The bucket is not in the configured region.\n\n"
                f"Set AWS_DEFAULT_REGION in .env to the region "
                f"'{S3_BUCKET}' actually lives in."
            )

        return f"S3 error while listing {sat_root}: {error}"

    except BotoCoreError as error:
        return f"Could not reach S3: {error}"

    if not keys:
        return (
            f"No .xlsx objects were found under:\n  {sat_root}\n\n"
            "Expected layout: <source>/<month>/*.xlsx\n\n"
            "Upload the reports with:\n"
            "  python -m scripts.sync_to_s3"
        )

    return (
        f"{len(keys)} Excel objects were found and are readable, but none "
        "produced usable rows. Check that the reports are not empty and "
        "that filenames contain 'Category' or 'Subcategory'."
    )


@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner="Loading SAT data...")
def load_all_data(sat_root):
    """
    Read every monthly SAT report from S3 and return
    (category_df, subcategory_df).

    `sat_root` is the cache key, so the cache invalidates by itself if the
    bucket or prefix ever changes. Call refresh_data() to force a re-read.
    """

    if sat_root is None:
        print("SAT data location is not configured.")
        return pd.DataFrame(), pd.DataFrame()

    print(f"Reading SAT data from: {sat_root}")

    try:
        client = get_client()
        keys = _keys(client, S3_BUCKET, S3_PREFIX)
    except (RuntimeError, BotoCoreError, ClientError) as error:
        print(f"Could not list {sat_root}: {error}")
        return pd.DataFrame(), pd.DataFrame()

    category_frames = []
    subcategory_frames = []

    files_seen = 0
    files_skipped = 0
    errors = []

    for key in keys:

        name = key.rsplit("/", 1)[-1]
        source, month = _source_and_month(key, S3_PREFIX)

        files_seen += 1

        report_type = classify_report(name)

        frames = {
            "Subcategory": subcategory_frames,
            "Category": category_frames,
        }.get(report_type)

        if frames is None:
            files_skipped += 1
            print(f"Skipped (unrecognised name): {name}")
            continue

        try:
            body = client.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read()
            # Read from memory: an object has no path for pandas to open,
            # and a workbook is small enough not to need a temporary file.
            df = pd.read_excel(io.BytesIO(body))
        except (BotoCoreError, ClientError, ValueError, OSError) as exc:
            errors.append(f"{key}: {exc}")
            print(f"Error reading object {key}: {exc}")
            continue

        if df.empty:
            files_skipped += 1
            print(f"Skipped (empty): {name}")
            continue

        df["Source"] = source
        df["Month"] = month
        df["File_Name"] = name
        df["business_unit"] = _business_unit(df, source)
        df["lens"] = _lens(df)

        frames.append(df)

        print(f"Loaded {report_type}: {source} | {month} | {name}")

    category_df = (
        pd.concat(category_frames, ignore_index=True)
        if category_frames
        else pd.DataFrame()
    )

    subcategory_df = (
        pd.concat(subcategory_frames, ignore_index=True)
        if subcategory_frames
        else pd.DataFrame()
    )

    print(
        f"Objects found: {files_seen} | skipped: {files_skipped} | "
        f"errors: {len(errors)}"
    )
    print(f"Category rows loaded: {len(category_df)}")
    print(f"Subcategory rows loaded: {len(subcategory_df)}")

    return category_df, subcategory_df
