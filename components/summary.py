"""
The Executive Summary.

Every sentence describes the *filtered* view, so the panel says what is
currently on screen rather than repeating a fixed set of facts about the whole
dataset. Sentences that stop making sense under a narrow selection - "the
best-performing category" when one category is selected - are dropped rather
than printed as trivia.
"""

import streamlit as st

from config.labels import unit_label
from config.settings import ACCURACY_TARGET
from scripts.processors.filter_data import wanted

# Filter key -> (name used in the scope line, how its values are spelled), in
# the order the filter row draws them. Business unit is the only one the data
# spells differently from the way it is shown.
SCOPE_LABELS = [
    ("month", "Month", str),
    ("business_unit", "Business Unit", unit_label),
    ("category", "Category", str),
    ("subcategory", "Subcategory", str),
    ("country", "Country", str),
    ("lens", "Lens", str),
]

# Names spelled out before a list collapses into a count. Past three the
# sentence stops being readable and the charts below are the better answer.
MAX_NAMED = 3


def _join(names, limit=MAX_NAMED):
    """["a", "b"] -> "a and b"; a long list -> "a, b, c and 4 more"."""

    names = list(names)

    if not names:
        return ""

    if len(names) > limit:
        return f"{', '.join(names[:limit])} and {len(names) - limit} more"

    if len(names) == 1:
        return names[0]

    return f"{', '.join(names[:-1])} and {names[-1]}"


def _plural(count, singular, plural):
    return f"{count} {singular if count == 1 else plural}"


def _scope(filters):
    """
    The active filters, as chips above the highlights.

    A chip per filter rather than one run-on sentence: these are the controls
    the reader just set, and a row of them reads as the state of the page
    instead of as prose about it.
    """

    chips = []

    for key, label, spelling in SCOPE_LABELS:

        # wanted() is the same resolver the filtering itself uses, so the
        # scope line can never claim a filter the data was not narrowed by.
        values = wanted(filters.get(key))

        if not values:
            continue

        chips.append(
            f'<span class="chip"><b>{label}</b>'
            f"{_join(spelling(v) for v in values)}</span>"
        )

    if not chips:
        chips = [
            '<span class="scope-empty">No filters set - every month, '
            "business unit, category, country and lens is included.</span>"
        ]

    return f'<div class="scope">{"".join(chips)}</div>'


def _highlights(metrics, filters):
    """The bullet list, built from whatever the current selection supports."""

    lines = []

    gap = metrics["overall_accuracy"] - ACCURACY_TARGET
    lines.append(
        f"Accuracy across this selection is "
        f"**{metrics['overall_accuracy']:.2f}%** - "
        f"**{abs(gap):.2f} pts {'above' if gap >= 0 else 'below'}** "
        f"the {ACCURACY_TARGET:g}% target."
    )

    change = metrics.get("accuracy_change")

    # The headline above averages every month in view, so the latest month is
    # stated separately rather than left to be inferred from it.
    if change is not None:
        lines.append(
            f"**{metrics['latest_month']}** came in at "
            f"**{metrics['latest_accuracy']:.1f}%**, **{abs(change):.1f} pts "
            f"{'up on' if change >= 0 else 'down on'} "
            f"{metrics['previous_month']}**."
        )

    categories = metrics["category_scores"]

    # Naming a leader needs something to lead. With one category selected the
    # comparison is replaced by that category's own numbers.
    if len(categories) > 1:
        spread = categories.iloc[0] - categories.iloc[-1]
        lines.append(
            f"**{categories.index[0]}** leads at **{categories.iloc[0]:.1f}%** "
            f"and **{categories.index[-1]}** trails at "
            f"**{categories.iloc[-1]:.1f}%** - a **{spread:.1f} pt** spread "
            f"across {_plural(len(categories), 'category', 'categories')}."
        )
    elif len(categories) == 1:
        # Deliberately not "across N subcategories": the category score comes
        # from the Category reports, not from averaging the subcategories.
        lines.append(
            f"**{categories.index[0]}** scores **{categories.iloc[0]:.1f}%** "
            f"at category level, with "
            f"{_plural(metrics['subcategories'], 'subcategory', 'subcategories')}"
            f" in view."
        )

    units = metrics["unit_scores"]

    if len(units) > 1:
        lines.append(
            f"By business unit, **{units.index[0]}** is strongest at "
            f"**{units.iloc[0]:.1f}%** and **{units.index[-1]}** weakest at "
            f"**{units.iloc[-1]:.1f}%**."
        )
    elif len(units) == 1:
        lines.append(f"Every row in view comes from **{units.index[0]}**.")

    countries = metrics["country_scores"]
    chosen_countries = wanted(filters.get("country"))

    if len(chosen_countries or []) == 1:
        lines.append(f"Figures are for **{chosen_countries[0]}** only.")
    elif chosen_countries:
        lines.append(
            f"Figures cover the **{len(chosen_countries)} selected "
            f"countries**: {_join(chosen_countries)}."
        )
    elif len(countries) > 1:
        lines.append(
            f"Spans **{len(countries)} countries**, from **{countries.index[0]}** "
            f"at **{countries.iloc[0]:.1f}%** down to **{countries.index[-1]}** "
            f"at **{countries.iloc[-1]:.1f}%**."
        )

    lines.append(_below_target(
        metrics["bad_categories"], len(categories), "category", "categories"
    ))
    lines.append(_below_target(
        metrics["bad_subcategories"],
        metrics["subcategories"],
        "subcategory",
        "subcategories",
    ))

    return [line for line in lines if line]


def _below_target(failing, total, singular, plural):
    """
    "3 of 12 categories are below target - X (41.2%), Y (55.0%), Z (60.1%)."

    `failing` arrives sorted worst-first, so the named ones are the ones worth
    naming.
    """

    if not total:
        return ""

    if not len(failing):
        if total == 1:
            return (
                f"The one {singular} in view is at or above the "
                f"{ACCURACY_TARGET:g}% target."
            )
        return (
            f"All **{total} {plural}** in view are at or above the "
            f"{ACCURACY_TARGET:g}% target."
        )

    named = _join(f"{name} ({score:.1f}%)" for name, score in failing.items())

    # "1 of 1 categories" is noise when the selection is a single item.
    count = (
        f"**{_plural(len(failing), singular, plural)}**"
        if total == 1
        else f"**{len(failing)} of {total}** {plural}"
    )

    verb = "sits" if len(failing) == 1 else "sit"

    return f"{count} {verb} below the {ACCURACY_TARGET:g}% target: {named}."


def show_summary(metrics, filters):

    # One heading, not two. The panel used to carry its own "Key Highlights"
    # heading directly under the section heading, at a different indent.
    st.subheader("Executive summary")

    bullets = "\n\n".join(f"- {line}" for line in _highlights(metrics, filters))

    st.markdown(
        f"""
<div class="section">

{_scope(filters)}

{bullets}

</div>
""",
        unsafe_allow_html=True,
    )
