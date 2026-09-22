"""
Filter application. Owns every filter so there is one answer to
"where are filters applied?".

Every filter in FILTER_SPEC runs on the wide frames before melting; `country`
runs after, because before the melt a country is a *column* and after it is a
*value*. `selected_countries` exposes that so the view does not have to know it.

Month, Category and Country are single-choice, so their value arrives as a
string; the rest are multi-selects and arrive as a list. `wanted()` is the one
place that difference is resolved, so nothing below it has to know which kind
of widget a filter was drawn with.
"""

from config.settings import (
    ALL_OPTION,
    BUSINESS_UNIT_COLUMNS,
    LENS_COLUMN,
    SUBCATEGORY_COLUMNS,
)


def normalize_month(value):
    """
    "January-2026" -> "January". Also the rule used to build the Month
    dropdown, so options and filtering can never disagree.
    """

    return str(value).strip().split("-")[0].strip()


# (filter key, candidate column names, value normaliser)
#
# business_unit spans two columns: product_type (inside the report) and
# Source (the top-level report folder, e.g. Social, FS_Retail). Social
# reports carry no product_type, so without Source they would never appear
# in the Business Unit dropdown at all.
FILTER_SPEC = [
    ("month", ["Month"], normalize_month),
    ("category", ["category"], None),
    ("subcategory", SUBCATEGORY_COLUMNS, None),
    ("business_unit", BUSINESS_UNIT_COLUMNS, None),
    # The loader's merged column, not the raw spellings it was built from -
    # matching "Lens" as well would select rows by a pre-merge value.
    ("lens", [LENS_COLUMN], None),
]


def wanted(value):
    """
    The values a filter is asking for, or None when it is asking for nothing.

    Single-choice dropdowns hand over a string and multi-selects a list, so
    every caller would otherwise have to test which it got. Both "Overall"
    and an empty multi-select mean "do not filter", and both arrive here as
    None.
    """

    if value is None or value == ALL_OPTION:
        return None

    if isinstance(value, str):
        return [value]

    values = [v for v in value if v and v != ALL_OPTION]

    return values or None


def _select(df, columns, values, normaliser=None):
    """
    Keep rows where ANY of `columns` holds ANY of `values`.

    Matching across columns rather than picking the first present one is what
    lets one dropdown span two columns - Business Unit draws on product_type
    and Source, and a report has only one of them.
    """

    mask = None

    for column in columns:

        if column not in df.columns:
            continue

        series = df[column].astype(str).str.strip()

        if normaliser is not None:
            series = series.map(normaliser)

        match = series.isin(values)
        mask = match if mask is None else (mask | match)

    if mask is None:
        return df

    return df[mask]


def apply_filters(category_df, subcategory_df, filters):
    """Apply every pre-melt filter to both frames."""

    category = category_df
    subcategory = subcategory_df

    for key, columns, normaliser in FILTER_SPEC:

        values = wanted(filters.get(key))

        if values is None:
            continue

        category = _select(category, columns, values, normaliser)
        subcategory = _select(subcategory, columns, values, normaliser)

    if wanted(filters.get("subcategory")) is not None:
        category = _parent_categories(category, subcategory)

    return category, subcategory


def _parent_categories(category, subcategory):
    """
    Narrow the Category frame to the categories the selected subcategories
    belong to.

    Only the Subcategory reports carry a subcategory column, so _select leaves
    the Category frame untouched - picking a subcategory would otherwise leave
    the category chart and the KPI cards showing every category, as if no
    filter had been applied.
    """

    if "category" not in category.columns or "category" not in subcategory.columns:
        return category

    parents = set(subcategory["category"].astype(str).str.strip())

    return category[category["category"].astype(str).str.strip().isin(parents)]


def selected_countries(filters, available):
    """
    Country columns to melt: just the selected ones, or all of them.

    Restricting this before the melt avoids expanding every row once per
    country and then discarding most of them again.

    Order follows `available` - the reports' own column order - rather than
    the order the user happened to tick the boxes in, so the melt is stable.
    """

    values = wanted(filters.get("country"))

    if values is None:
        return available

    chosen = [country for country in available if country in set(values)]

    # A selection that matches nothing available would melt zero columns and
    # empty the page. Falling back to every country keeps the previous
    # behaviour for a value that is no longer in the data.
    return chosen or available
