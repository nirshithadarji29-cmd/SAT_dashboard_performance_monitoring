"""
What to do about what the charts show.

Every line names something specific in the current selection - a unit, a
category, a country, a month - so the block changes when the filters change.
The previous version printed three fixed sentences that were true of every
possible view, which is another way of saying they carried no information.
"""

import streamlit as st

from config.settings import ACCURACY_TARGET

# How many names a single recommendation spells out.
MAX_NAMED = 3


def _worst(scores, count=MAX_NAMED):
    """The `count` lowest-scoring entries, worst first."""

    return scores.sort_values().head(count)


def _named(scores):
    """"Color Cosmetics (31.3%), Baby Food (65.6%)"."""

    return ", ".join(f"**{name}** ({value:.1f}%)" for name, value in scores.items())


def _priority(metrics):
    """
    The single biggest lever: the business unit furthest below target, and
    the categories dragging it there.
    """

    units = metrics["unit_scores"]

    if not len(units):
        return None

    unit = units.index[-1]
    score = units.iloc[-1]

    if score >= ACCURACY_TARGET:
        return None

    unit_rows = metrics["category_unit_scores"]
    unit_rows = unit_rows[unit_rows["business_unit"] == unit]

    if unit_rows.empty:
        return f"**{unit}** is the weakest unit in view at **{score:.1f}%**."

    worst = _worst(unit_rows.set_index("category")["accuracy"])

    return (
        f"**{unit}** is **{ACCURACY_TARGET - score:.1f} pts** below target at "
        f"**{score:.1f}%** - the weakest unit in view. Its lowest categories "
        f"are {_named(worst)}."
    )


def _movement(metrics):
    """What changed since the previous month in view."""

    change = metrics.get("accuracy_change")

    if change is None:
        return None

    latest = metrics["latest_month"]
    previous = metrics["previous_month"]

    if change < -1:
        return (
            f"Accuracy fell **{abs(change):.1f} pts** between {previous} and "
            f"{latest}. Treat {latest} as the number to explain, not the "
            f"{metrics['overall_accuracy']:.1f}% average across all months."
        )

    if change > 1:
        return (
            f"{latest} is **{change:.1f} pts** better than {previous} - worth "
            "identifying what changed and whether it holds."
        )

    return (
        f"{latest} is flat on {previous} ({change:+.1f} pts): nothing in the "
        "current selection moved materially last month."
    )


def _geography(metrics):
    """Where the losses are concentrated."""

    countries = metrics["country_scores"]

    if len(countries) < 2:
        return None

    failing = countries[countries < ACCURACY_TARGET]

    if failing.empty:
        return None

    worst = _worst(failing)
    counts = metrics["country_counts"]

    # Sample size is the first thing to check before acting on a country, and
    # coverage here is very uneven - hundreds of readings for some, tens for
    # others.
    detail = ", ".join(
        f"**{name}** ({value:.1f}%, n={int(counts.get(name, 0))})"
        for name, value in worst.items()
    )

    return (
        f"**{len(failing)} of {len(countries)} countries** are below target. "
        f"The lowest are {detail}."
    )


def _subcategories(metrics):
    """The deepest gaps at subcategory level."""

    failing = metrics["bad_subcategories"]

    if not len(failing):
        return None

    worst = _worst(failing)
    gap = ACCURACY_TARGET - worst.iloc[0]

    return (
        f"At subcategory level the deepest gaps are {_named(worst)} - "
        f"**{gap:.0f} pts** below target at the worst. These are where a "
        "prompt or taxonomy fix has the most room to pay back."
    )


def show_recommendations(metrics):
    # Everything below reads from `metrics`, which is already computed from the
    # filtered frames - so the block follows the filters without being handed
    # them.

    st.subheader("Where to focus")

    if metrics["overall_accuracy"] < ACCURACY_TARGET:
        st.warning(
            f"This selection averages **{metrics['overall_accuracy']:.2f}%**, "
            f"**{ACCURACY_TARGET - metrics['overall_accuracy']:.2f} pts** below "
            f"the {ACCURACY_TARGET:g}% target."
        )
    else:
        st.success(
            f"This selection averages **{metrics['overall_accuracy']:.2f}%**, "
            f"above the {ACCURACY_TARGET:g}% target. "
            f"**{metrics['needs_improvement']}** categories still sit below it."
        )

    lines = [
        line for line in (
            _priority(metrics),
            _movement(metrics),
            _geography(metrics),
            _subcategories(metrics),
        ) if line
    ]

    if not lines:
        st.info(
            "Everything in the current selection is at or above target. The "
            "strongest category is "
            f"**{metrics['top_category']}** - worth looking at what its "
            "prompts do differently."
        )
        return

    st.markdown(
        '<div class="section">\n\n'
        + "\n\n".join(f"- {line}" for line in lines)
        + "\n\n</div>",
        unsafe_allow_html=True,
    )
