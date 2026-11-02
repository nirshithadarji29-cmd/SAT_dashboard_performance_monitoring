import calendar
import re

import pandas as pd

from config.settings import NON_COUNTRY_COLUMNS
from scripts.processors.filter_data import normalize_month

# January -> 1, February -> 2, ... derived from the stdlib rather than a
# hand-written dict. Lives here rather than in the filter row because the
# trend chart needs the same order the Month dropdown uses.
MONTH_ORDER = {
    name: number
    for number, name in enumerate(calendar.month_name)
    if name
}

# Wide-frame column -> its name once melted. The long frames are lowercase
# throughout (category, subcategory, country, accuracy), so Month joins them.
LONG_NAMES = {"Month": "month"}

# What pandas names a column whose header cell is blank. One subcategory
# report carries a trailing empty column, which the "everything else is a
# country" rule below would otherwise offer in the Country dropdown.
BLANK_HEADER = "unnamed:"


def sort_months(names):
    """Distinct month names in calendar order; unrecognised names go last."""

    return sorted(set(names), key=lambda m: (MONTH_ORDER.get(m, 99), str(m)))


def country_columns(*frames):
    """
    Country columns present in the given frames, derived from the data.

    Reports are wide: one column per country, plus a handful of structural
    columns. Anything that is not structural is a country, so adding a
    country to the reports needs no code change - which also means a stray
    column becomes a country, hence the blank-header check.

    Order follows the reports themselves, so the Country dropdown and the
    melt always agree.
    """

    countries = []

    for frame in frames:
        if frame is None:
            continue
        for column in frame.columns:
            name = str(column).strip().lower()
            if name in NON_COUNTRY_COLUMNS or name.startswith(BLANK_HEADER):
                continue
            if column not in countries:
                countries.append(column)

    return countries


def _long_columns(id_vars):
    """Column names of the melted frame built from these id_vars."""

    return [LONG_NAMES.get(c, c) for c in id_vars] + ["country", "accuracy"]


def _melt_accuracy(df, id_vars, countries=None, optional=()):
    """
    Turn a wide report (one column per country) into long rows of
    (id_vars..., country, accuracy).

    `countries` restricts which country columns are melted. Passing a single
    country avoids expanding every row 25-fold only to discard 24 of them.

    `optional` columns ride along when the frame has them and are skipped
    when it does not - unlike `id_vars`, where a missing column means the
    frame is not the report it was taken for and nothing is melted. Lens is
    optional: only some reports carry it, and the ones that do not should
    still produce every other figure on the page.
    """

    if df.empty:
        return pd.DataFrame(columns=_long_columns(id_vars))

    if countries is None:
        countries = country_columns(df)

    value_vars = [c for c in countries if c in df.columns]
    ids = [c for c in id_vars if c in df.columns]

    if not value_vars or len(ids) != len(id_vars):
        return pd.DataFrame(columns=_long_columns(id_vars))

    ids += [c for c in optional if c in df.columns and c not in ids]

    melted = df.melt(
        id_vars=ids,
        value_vars=value_vars,
        var_name="country",
        value_name="accuracy",
    )

    melted["accuracy"] = pd.to_numeric(melted["accuracy"], errors="coerce")

    melted = melted.rename(columns=LONG_NAMES)

    if "month" in melted.columns:
        # The same rule the Month dropdown is built from, so the trend axis
        # and the filter can never disagree about what "January" is.
        melted["month"] = melted["month"].map(normalize_month)

    return melted.dropna(subset=["accuracy"])


def category_accuracy(df, countries=None):
    # business_unit is carried through the melt so the category chart can
    # break each category down by unit. It is set on every row by the loader
    # (see _business_unit), unlike product_type, which Social reports lack.
    #
    # Month is carried for the trend chart; without it every figure on the
    # page would be a single blend of every month loaded.
    #
    # lens rides along optionally, for the per-lens breakdown on the hero
    # card. A report with no lens column still melts without it.
    return _melt_accuracy(
        df,
        ["category", "product_type", "business_unit", "Month"],
        countries,
        optional=["lens"],
    )


def subcategory_accuracy(df, countries=None):
    # Subcategory reports have no product_type column.
    return _melt_accuracy(
        df, ["category", "subcategory", "business_unit", "Month"], countries
    )


def data_period(*frames):
    """
    What the loaded reports actually cover, for the header.

    The date in the header used to be today's - which reads as data freshness
    and is not. This reports the span of the reports themselves.
    """

    months = []
    files = set()
    years = set()

    for frame in frames:

        if frame is None or frame.empty:
            continue

        if "Month" in frame.columns:
            months.extend(
                normalize_month(m) for m in frame["Month"].dropna().unique()
            )

        if "File_Name" in frame.columns:
            for name in frame["File_Name"].dropna().unique():
                files.add(name)
                # The month folders carry no year, so it comes from the
                # filenames (FS_&_Retail_Category_Level_Report_June_2026.xlsx).
                years.update(re.findall(r"(20\d{2})", str(name)))

    ordered = sort_months(months)
    year = max(years) if years else ""

    if not ordered:
        return {"months": [], "latest": "No data", "span": "", "reports": 0}

    latest = f"{ordered[-1]} {year}".strip()

    span = (
        f"{ordered[0]} - {ordered[-1]} {year}".strip()
        if len(ordered) > 1
        else latest
    )

    return {
        "months": ordered,
        "latest": latest,
        "span": span,
        "reports": len(files),
    }
