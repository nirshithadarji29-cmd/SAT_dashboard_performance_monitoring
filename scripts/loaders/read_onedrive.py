import re
import sys

import pandas as pd
import streamlit as st

from config.settings import DATA_CACHE_TTL, LENS_COLUMNS, LENS_MERGES
from scripts.loaders.onedrive_path import describe_search, resolve_sat_root


@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner=False)
def get_sat_root():
    """
    Cached wrapper around resolve_sat_root().

    Resolution globs several OneDrive roots at multiple depths, so running it
    on every widget interaction would re-walk the synced tree each time.
    """

    return resolve_sat_root()


def refresh_data():
    """Invalidate every data cache so the next run re-reads from OneDrive."""

    get_sat_root.clear()
    load_all_data.clear()


def is_materialised(path):
    """
    True if the file's bytes are actually on disk.

    An .xlsx is a zip archive and always starts with "PK". OneDrive
    Files On-Demand leaves cloud-only files as placeholders: they report
    their real size but read back as zeros, so pandas fails with the
    unhelpful "Excel file format cannot be determined".
    """

    try:
        with open(path, "rb") as handle:
            return handle.read(2) == b"PK"
    except OSError:
        return False


def describe_data_problem(sat_root):
    """
    Explain why no data could be read from `sat_root`.

    Not cached and cheap (stat + 2 bytes per file), so it is safe to call
    from the error path in the UI.
    """

    if sat_root is None:
        return describe_search()

    files = [
        f for f in sat_root.rglob("*.xlsx")
        if not f.name.startswith("~$")
    ]

    if not files:
        return (
            f"No .xlsx files were found under:\n  {sat_root}\n\n"
            "Expected layout: <source>/<month>/*.xlsx"
        )

    placeholders = [f for f in files if not is_materialised(f)]

    if not placeholders:
        return (
            f"{len(files)} Excel files were found and are readable, but none "
            "produced usable rows. Check that the reports are not empty and "
            "that filenames contain 'Category' or 'Subcategory'."
        )

    lines = [
        f"{len(placeholders)} of {len(files)} Excel files are OneDrive "
        "cloud-only placeholders - their contents have not been downloaded "
        "to this machine, so they cannot be read.",
        "",
    ]

    # The fix differs per platform, and reading macOS instructions on Windows
    # (or the reverse) is worse than no instructions at all.
    if sys.platform == "darwin":
        lines += [
            "To fix on macOS:",
            "",
            "  1. In Finder, right-click the shared SAT folder in OneDrive and "
            "choose 'Always Keep on This Device'. Wait for the download to "
            "finish (solid green check, not a cloud icon).",
            "",
            "  2. Grant your terminal Full Disk Access:",
            "     System Settings > Privacy & Security > Full Disk Access,",
            "     enable Terminal (or iTerm), then restart it.",
            "     Without this, ~/Library/CloudStorage is not readable and the",
            "     app falls back to a copy that never downloads on demand.",
        ]
    else:
        lines += [
            "To fix on Windows:",
            "",
            "  1. In File Explorer, right-click the shared SAT folder under "
            "OneDrive and choose 'Always keep on this device'. Wait for the "
            "download to finish (a solid green check, not a cloud icon).",
            "",
            "  2. If the folder was added with 'Add shortcut to My files', "
            "open it once in Explorer so OneDrive starts syncing it.",
            "",
            "  3. Check that OneDrive is running and signed in - a paused "
            "client leaves every file as a placeholder.",
        ]

    return "\n".join(lines)


def _business_unit(df, source):
    """
    One business unit per row.

    Reports that carry a product_type (e.g. FS, Retail) use it. Reports that
    do not - Social has no product_type column - fall back to the folder they
    came from. Coalescing per row rather than offering both columns keeps the
    combined folder name "FS_Retail" out of the dropdown while still listing
    the FS and Retail rows it contains.
    """

    if "product_type" not in df.columns:
        return source

    values = df["product_type"].astype(str).str.strip()

    return values.mask(values.isin(["", "nan", "None", "NaN"]), source)


def _lens(df):
    """
    One lens column per row, whatever the report spelled it.

    Social reports carry "Lens" and the FS / Retail reports carry "lens", so a
    frame concatenated from both holds two half-empty columns and no single
    one to group by. LENS_COLUMNS is in preference order, and the first
    non-blank value wins.

    Values are then merged down to the three reported lenses via LENS_MERGES,
    here rather than at display time: a merged lens has to group and filter as
    one, not just print as one.

    Returns NA for a report that carries no lens at all, so the column exists
    on every frame and the melt can rely on it.
    """

    merged = pd.Series(pd.NA, index=df.index, dtype="object")

    for column in LENS_COLUMNS:

        if column not in df.columns:
            continue

        values = df[column].astype(str).str.strip()

        # astype(str) turns a missing cell into the text "nan", which would
        # otherwise win the coalesce as a perfectly good value.
        merged = merged.fillna(
            values.mask(values.isin(["", "nan", "None", "NaN", "<NA>"]))
        )

    # Matched case-insensitively so a report that starts capitalising its
    # values does not quietly reintroduce a fourth lens.
    return merged.map(
        lambda v: LENS_MERGES.get(str(v).lower(), v) if pd.notna(v) else v
    )


def classify_report(filename):
    """
    Return "Subcategory", "Category", or None for a report filename.

    Filenames are inconsistent across sources and months, e.g.

        Subcategory_Level_Report_SAT_Social_April_2026.xlsx
        Sub_Category_level_report_Social_SAT_JAN_2026.xlsx
        FS_&_Retail_Category_Level_Report_April_2026.xlsx

    so separators are stripped before matching. Subcategory MUST be tested
    first: the string "subcategory" contains "category", so testing category
    first silently misfiles every subcategory report as a category report.
    """

    normalised = re.sub(r"[^a-z]", "", filename.lower())

    if "subcategory" in normalised:
        return "Subcategory"

    if "category" in normalised:
        return "Category"

    return None


@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner="Loading SAT data...")
def load_all_data(sat_root):
    """
    Read every monthly SAT Excel report and return
    (category_df, subcategory_df).

    Expected folder layout under the SAT root:

        <source>/<month>/*.xlsx

    `sat_root` is the cache key, so the cache invalidates by itself if the
    folder ever moves. Call refresh_data() to force a re-read.
    """

    if sat_root is None:
        print("SAT data folder could not be located.")
        return pd.DataFrame(), pd.DataFrame()

    print(f"Reading SAT data from: {sat_root}")

    category_frames = []
    subcategory_frames = []

    files_seen = 0
    files_skipped = 0
    placeholders = 0
    errors = []

    for source_folder in sorted(sat_root.iterdir()):

        if not source_folder.is_dir():
            continue

        source = source_folder.name

        for month_folder in sorted(source_folder.iterdir()):

            if not month_folder.is_dir():
                continue

            month = month_folder.name

            for file in sorted(month_folder.glob("*.xlsx")):

                # Skip Excel lock files (~$Report.xlsx) left by open workbooks.
                if file.name.startswith("~$"):
                    continue

                files_seen += 1

                if not is_materialised(file):
                    placeholders += 1
                    print(f"Skipped (not downloaded from OneDrive): {file.name}")
                    continue

                report_type = classify_report(file.name)

                frames = {
                    "Subcategory": subcategory_frames,
                    "Category": category_frames,
                }.get(report_type)

                if frames is None:
                    files_skipped += 1
                    print(f"Skipped (unrecognised name): {file.name}")
                    continue

                try:
                    df = pd.read_excel(file)
                except Exception as exc:
                    errors.append(f"{file}: {exc}")
                    print(f"Error reading file {file}: {exc}")
                    continue

                if df.empty:
                    files_skipped += 1
                    print(f"Skipped (empty): {file.name}")
                    continue

                df["Source"] = source
                df["Month"] = month
                df["File_Name"] = file.name
                df["business_unit"] = _business_unit(df, source)
                df["lens"] = _lens(df)

                frames.append(df)

                print(f"Loaded {report_type}: {source} | {month} | {file.name}")

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
        f"Files found: {files_seen} | skipped: {files_skipped} | "
        f"not downloaded: {placeholders} | errors: {len(errors)}"
    )
    print(f"Category rows loaded: {len(category_df)}")
    print(f"Subcategory rows loaded: {len(subcategory_df)}")

    return category_df, subcategory_df
