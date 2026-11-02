"""
Aggregate the melted frames once. The view renders these results rather than
recomputing its own groupbys.

Every aggregate carries an observation count alongside its mean: a category
scored from six country readings and one scored from five hundred look
identical on a chart otherwise.
"""

import pandas as pd

from config.labels import is_aggregate, region_of, unit_label
from config.settings import ACCURACY_TARGET, LENS_UNIT
from scripts.processors.dashboard_data import sort_months


def _scores(long, keys):
    """Mean accuracy and observation count per key combination."""

    return (
        long
        .groupby(keys, as_index=False)
        .agg(accuracy=("accuracy", "mean"), observations=("accuracy", "size"))
    )


def _ranked(long, key):
    """Mean accuracy per key as a Series, best first."""

    return long.groupby(key)["accuracy"].mean().sort_values(ascending=False)


def _month_change(long, months):
    """
    Accuracy in the latest month in view and the change from the one before.

    Both months come from the *current* view: with a single month selected
    there is no previous month to compare against, and the view says so
    rather than reaching outside the filter for a number the user excluded.
    """

    if not months:
        return {"latest_month": None, "previous_month": None,
                "latest_accuracy": None, "accuracy_change": None}

    latest = months[-1]
    previous = months[-2] if len(months) > 1 else None

    by_month = long.groupby("month")["accuracy"].mean()

    return {
        "latest_month": latest,
        "previous_month": previous,
        "latest_accuracy": round(by_month.get(latest), 2),
        "accuracy_change": (
            round(by_month.get(latest) - by_month.get(previous), 2)
            if previous is not None
            else None
        ),
    }


def _below_target_change(long, latest, previous):
    """Change in the number of below-target categories, latest vs previous."""

    if previous is None:
        return None

    per_month = long.groupby(["month", "category"])["accuracy"].mean()
    failing = per_month[per_month < ACCURACY_TARGET].groupby("month").size()

    return int(failing.get(latest, 0)) - int(failing.get(previous, 0))


def _unit_scorecard(unit_month, latest, previous):
    """
    One row per business unit: where it stands now, how it moved, and how far
    it is from target.

    A single 85% line is held up against every unit, but the units are not the
    same problem - this is what makes the difference legible without reading
    it off a chart.
    """

    if unit_month.empty or latest is None:
        return pd.DataFrame()

    accuracy = unit_month.pivot(
        index="business_unit", columns="month", values="accuracy"
    )
    counts = unit_month.pivot(
        index="business_unit", columns="month", values="observations"
    )

    if latest not in accuracy.columns:
        return pd.DataFrame()

    table = pd.DataFrame(index=accuracy.index)
    table[f"{latest} accuracy (%)"] = accuracy[latest].round(1)

    if previous is not None and previous in accuracy.columns:
        table[f"Change vs {previous} (pts)"] = (
            accuracy[latest] - accuracy[previous]
        ).round(1)

    table["Gap to target (pts)"] = (accuracy[latest] - ACCURACY_TARGET).round(1)
    table["Observations"] = counts[latest].astype("Int64")

    table.index.name = "Business unit"

    return table.sort_values(table.columns[0], ascending=False)


def _lens_scores(long, unit):
    """
    Mean accuracy per lens for one business unit, best first.

    Restricted to a single unit because the two lens vocabularies are not the
    same measure: the FS and Retail reports score five lenses of their own and
    Social scores three. Ranking all eight in one list would invite a
    comparison the reports do not support.

    Returns an empty frame - not a row of zeros - when the unit is filtered
    out or its rows carry no lens, so the view can leave the block out
    entirely rather than draw an empty one.
    """

    empty = pd.DataFrame(columns=["lens", "accuracy", "observations"])

    if "lens" not in long.columns or "business_unit" not in long.columns:
        return empty

    rows = long[long["business_unit"].astype(str).str.strip() == unit]

    lens = rows["lens"].astype(str).str.strip()
    rows = rows[rows["lens"].notna() & lens.ne("") & lens.ne("nan")]

    if rows.empty:
        return empty

    return (
        _scores(rows, ["lens"])
        .sort_values("accuracy", ascending=False)
        .reset_index(drop=True)
    )


# How many pairs each region lists. Ten per region, not ten overall: a single
# global top ten is dominated by whichever region happens to score highest,
# and a customer asking about Europe is not helped by being told Europe has
# one entry in it.
LEADERS_PER_REGION = 10

# A pair scored from one or two readings can top a leaderboard on noise alone.
# The unfiltered data carries at least 16 readings per pair, so this only ever
# bites on a narrow filter selection - and if it would empty the board, it is
# dropped rather than leaving the section blank.
MIN_LEADER_READINGS = 5


def _regional_leaders(long):
    """
    The strongest country x category pairs, ranked within each region.

    Each region is its own leaderboard, so the rank beside a pair says where
    it stands in its own region - Europe's number one is Europe's number one
    whether or not it would place anywhere on a combined list.
    """

    if long.empty or "country" not in long.columns:
        return []

    pairs = _scores(long, ["country", "category"])

    if pairs.empty:
        return []

    # Only apply the floor if something survives it.
    solid = pairs[pairs["observations"] >= MIN_LEADER_READINGS]
    pairs = solid if not solid.empty else pairs

    # Ties broken by the better-evidenced pair, so the order is stable rather
    # than whatever the groupby happened to produce.
    pairs = pairs.sort_values(
        ["accuracy", "observations"], ascending=[False, False]
    )
    pairs["region"] = pairs["country"].map(region_of)

    regions = []

    # Regions in the order their best pair scores, so the strongest region
    # leads - the same best-first rule the rest of the page is ordered by.
    for region in pairs["region"].drop_duplicates():
        rows = pairs[pairs["region"] == region].head(LEADERS_PER_REGION)

        regions.append({
            "region": region,
            # The whole region, not just what is listed: the panel says "top
            # 10 of 34" rather than implying the region has only ten pairs.
            "total": int((pairs["region"] == region).sum()),
            "leaders": [
                {
                    "rank": index,
                    "country": row.country,
                    "category": row.category,
                    "accuracy": float(row.accuracy),
                    "observations": int(row.observations),
                }
                for index, row in enumerate(rows.itertuples(), start=1)
            ],
        })

    return regions


def calculate_metrics(category_long, subcategory_long):

    category_long = category_long.copy()
    subcategory_long = subcategory_long.copy()

    # Display spelling is applied once, here, at the boundary between the data
    # and the view. Filtering has already happened by this point and matches on
    # the raw values, so nothing downstream has to know both spellings.
    for frame in (category_long, subcategory_long):
        if "business_unit" in frame.columns:
            frame["business_unit"] = frame["business_unit"].map(unit_label)

    # The reports' own "All" rows are per-category aggregates. Left in, they
    # would compete with real subcategories in the Top and Bottom 10.
    real_subcategories = subcategory_long[
        ~subcategory_long["subcategory"].map(is_aggregate)
    ]

    category_scores = _ranked(category_long, "category")
    subcategory_scores = _ranked(real_subcategories, "subcategory")

    months = sort_months(category_long["month"].dropna())

    # One row per (category, business unit) for the grouped category chart.
    # Left long rather than pivoted - plotly express colours by a column, and
    # a category with no rows for a unit simply has no row here, so that bar
    # is not drawn instead of being drawn as a zero.
    category_unit_scores = _scores(category_long, ["category", "business_unit"])

    # The trend: one point per (month, business unit).
    unit_month_scores = _scores(category_long, ["month", "business_unit"])

    change = _month_change(category_long, months)

    bad_categories = category_scores[category_scores < ACCURACY_TARGET]
    bad_subcategories = subcategory_scores[subcategory_scores < ACCURACY_TARGET]

    return {
        "overall_accuracy": round(category_long["accuracy"].mean(), 2),
        "categories": category_long["category"].nunique(),
        "subcategories": real_subcategories["subcategory"].nunique(),
        "countries": category_long["country"].nunique(),
        "top_category": category_scores.index[0] if len(category_scores) else "N/A",
        "needs_improvement": len(bad_categories),
        "needs_improvement_change": _below_target_change(
            category_long, change["latest_month"], change["previous_month"]
        ),
        "months": months,
        "month_scores": (
            category_long.groupby("month")["accuracy"].mean().reindex(months)
        ),
        "category_scores": category_scores,
        "category_counts": category_long.groupby("category")["accuracy"].size(),
        "category_unit_scores": category_unit_scores,
        "unit_month_scores": unit_month_scores,
        "unit_scorecard": _unit_scorecard(
            unit_month_scores, change["latest_month"], change["previous_month"]
        ),
        # Both sorted best-first like category_scores, so a caller can read the
        # strongest and weakest off the two ends.
        "unit_scores": _ranked(category_long, "business_unit"),
        "country_scores": _ranked(category_long, "country"),
        "country_counts": category_long.groupby("country")["accuracy"].size(),
        "subcategory_scores": subcategory_scores,
        "subcategory_counts": (
            real_subcategories.groupby("subcategory")["accuracy"].size()
        ),
        "regional_leaders": _regional_leaders(category_long),
        "lens_unit": LENS_UNIT,
        "lens_scores": _lens_scores(category_long, LENS_UNIT),
        "bad_categories": bad_categories.sort_values(),
        "bad_subcategories": bad_subcategories.sort_values(),
        **change,
    }
