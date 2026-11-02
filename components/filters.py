import streamlit as st

from config.labels import is_aggregate, lens_label, unit_label
from config.settings import (
    ALL_OPTION,
    BUSINESS_UNIT_COLUMNS,
    DATA_CACHE_TTL,
    LENS_COLUMN,
    SUBCATEGORY_COLUMNS,
)
from scripts.processors.dashboard_data import country_columns, sort_months
from scripts.processors.filter_data import normalize_month, wanted

# Dropdowns per filter row.
PER_ROW = 3

# Filters that take exactly one value. The rest stay multi-select: a report
# is read one month, one category and one country at a time, while the
# remaining three are the ones people genuinely combine.
SINGLE_FILTERS = {"month", "category", "country"}

# Filters whose stored value is the report's own spelling but whose dropdown
# shows a tidier one. Only the label changes - the value handed to the filter
# is untouched, so matching never depends on how it is displayed.
DISPLAY_FILTERS = {"business_unit": unit_label, "lens": lens_label}


def _options(frames, columns, normaliser=None):
    """
    Sorted distinct values across every matching column in `frames`.

    Unions all listed columns rather than stopping at the first, so one
    dropdown can span two columns - Business Unit lists product_type values
    and Source values together.

    `.unique()` runs before normalising, so the normaliser sees a handful of
    values rather than one per row.
    """

    values = set()

    for frame in frames:
        for column in columns:

            if column not in frame.columns:
                continue

            found = frame[column].dropna().astype(str).str.strip().unique()

            if normaliser is not None:
                found = [normaliser(v) for v in found]

            values.update(v for v in found if v)

    return sorted(values)


@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner=False)
def build_options(category_df, subcategory_df):
    """
    Every dropdown's options. Derived from the unfiltered data, so the result
    is stable for the life of the data cache and is cached alongside it.
    """

    frames = [category_df, subcategory_df]

    return {
        "month": sort_months(_options(frames, ["Month"], normalize_month)),
        "business_unit": _options(frames, BUSINESS_UNIT_COLUMNS),
        "category": _options(frames, ["category"]),
        # Every subcategory in the reports. Shown as-is while Category is on
        # "Overall"; narrowed to one category's own by _subcategory_choices
        # once a category is picked.
        #
        # "All" is dropped: it is the reports' own per-category aggregate row,
        # not a subcategory anyone would mean to select.
        "subcategory": [
            value for value in _options(frames, SUBCATEGORY_COLUMNS)
            if not is_aggregate(value)
        ],
        "country": country_columns(category_df, subcategory_df),
        # The merged column only, never the reports' raw spellings: the
        # dropdown lists the three lenses the app actually groups by, so a
        # value folded into another can no longer be picked and then match
        # nothing.
        "lens": _options(frames, [LENS_COLUMN]),
    }


@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner=False)
def subcategories_by_category(subcategory_df):
    """
    category -> the subcategories reported under it.

    Built from the Subcategory reports, which are the only ones carrying both
    columns, and cached with the data: the pairing changes when the reports
    do, not when a dropdown moves.
    """

    columns = [c for c in SUBCATEGORY_COLUMNS if c in subcategory_df.columns]

    if "category" not in subcategory_df.columns or not columns:
        return {}

    pairs = subcategory_df[["category", columns[0]]].dropna()
    pairs = pairs.astype(str).apply(lambda column: column.str.strip())

    grouped = {}

    for category, subcategory in pairs.itertuples(index=False):

        if not category or not subcategory or is_aggregate(subcategory):
            continue

        grouped.setdefault(category, set()).add(subcategory)

    return {category: sorted(values) for category, values in grouped.items()}


def _subcategory_choices(every, by_category, category):
    """
    The subcategories worth offering for the current Category selection.

    Cascading rather than listing all 113: with a category chosen, the other
    hundred are rows the page cannot show anyway, and scrolling past them to
    find one of six is the whole cost of the flat list.

    Falls back to the full set when Category is on "Overall", and when a
    selected category has no subcategories of its own - an empty dropdown
    would look broken rather than informative.
    """

    selected = wanted(category)

    if not selected:
        return every

    narrowed = sorted({
        value
        for name in selected
        for value in by_category.get(name, ())
    })

    return narrowed or every


def _prune(key, choices):
    """
    Drop a stored selection the narrowed options no longer offer.

    Streamlit raises when a widget's stored value is not among its options,
    and changing Category is exactly what strands a subcategory picked under
    the previous one. Pruning before the widget is built turns that into the
    selection quietly clearing, which is what changing the parent filter
    means anyway.
    """

    stored = st.session_state.get(key)

    if not isinstance(stored, list):
        return

    kept = [value for value in stored if value in set(choices)]

    if len(kept) != len(stored):
        st.session_state[key] = kept


def show_filters(category_df, subcategory_df):
    """Render the filter row and return the selected values."""

    options = build_options(category_df, subcategory_df)
    by_category = subcategories_by_category(subcategory_df)

    # Category MUST come before subcategory: the subcategory dropdown is built
    # from whatever category is holding when its turn comes round, and a
    # widget cannot read a selection that has not been drawn yet.
    labels = [
        ("month", "Month"),
        ("business_unit", "Business unit"),
        ("category", "Category"),
        ("subcategory", "Subcategory"),
        ("country", "Country"),
        ("lens", "Lens"),
    ]

    selected = {}

    # One bordered block, so six dropdowns read as a control panel rather
    # than as loose widgets floating above the figures.
    with st.container(border=True):

        # Laid out in rows of three rather than one row per filter: six
        # dropdowns side by side squeeze the long subcategory names down to
        # an ellipsis.
        for start in range(0, len(labels), PER_ROW):
            row = labels[start:start + PER_ROW]

            # Always PER_ROW columns wide, so a short final row keeps the
            # same dropdown width as a full one instead of stretching to
            # fill. Top-aligned so a control that has grown a row of chips
            # does not drag its neighbours' labels down with it.
            columns = st.columns(PER_ROW, vertical_alignment="top")

            for column, (key, label) in zip(columns, row):

                choices = options[key]

                if key == "subcategory":
                    choices = _subcategory_choices(
                        choices, by_category, selected.get("category")
                    )
                    _prune(f"{key}_multi", choices)

                with column:
                    selected[key] = _dropdown(key, label, choices)

    return selected


def _dropdown(key, label, choices):
    """
    One filter widget: a single-choice box for SINGLE_FILTERS, a multi-select
    for the rest.
    """

    # format_func changes only what is drawn. The option itself stays the
    # report's own spelling, so the value reaching apply_filters is the one
    # the data holds - "Food Service" is never matched against "food_service".
    format_func = DISPLAY_FILTERS.get(key, str)

    if key in SINGLE_FILTERS:
        # ALL_OPTION leads the list because a single-choice box always holds
        # a value - without it there would be no way back to the unfiltered
        # view once a month or a country had been picked. wanted() reads the
        # sentinel as "do not filter".
        return st.selectbox(
            label,
            [ALL_OPTION] + list(choices),
            # A key of its own, not the f"{key}_multi" the multi-select uses:
            # a session left open across this change would otherwise hand a
            # stored list to a widget that expects one value.
            key=f"{key}_one",
            format_func=format_func,
        )

    # No ALL_OPTION entry here: selecting nothing already means "do not
    # filter", and offering "Overall" alongside real values would raise the
    # question of what "Overall + Dairy" is meant to mean. The placeholder
    # says so where the sentinel used to.
    return st.multiselect(
        label,
        choices,
        key=f"{key}_multi",
        placeholder=ALL_OPTION,
        format_func=format_func,
    )
