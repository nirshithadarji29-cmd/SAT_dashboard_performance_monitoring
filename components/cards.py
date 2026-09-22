"""
The figures at the top of the page.

Six matching cards used to sit here, one per metric, each with its own accent
colour. That gave "113 subcategories" the same weight as accuracy against
target, and the colours meant nothing - purple did not stand for subcategory.

What replaces it says the same things in the order they matter: the accuracy
figure against its target, the count of categories below it, and the coverage
of the current view as one quiet line.
"""

import streamlit as st

from config.labels import lens_label
from config.settings import ACCURACY_TARGET

# Movement cues as classes rather than inline colours: the widget CSS has to
# win against Streamlit's own, so the colours live in style.css beside it.
#
# Red and green are indistinguishable to a deuteranope, so the arrow and the
# wording carry the direction and the colour only reinforces it.
GOOD = "up"
BAD = "down"
FLAT = "flat"

# How many below-target categories the card names on its face before the rest
# are left to the drill-down.
PREVIEW_ROWS = 3

# Half the categories below target is the line between "a few to chase" and
# "the target is not being met", so that is where the badge changes.
WIDESPREAD = 0.5

def _delta(change, digits, higher_is_better=True):
    """The coloured arrow fragment, e.g. "▲ 2.6"."""

    if round(change, digits) == 0:
        return f'<span class="{FLAT}">■ no change</span>'

    rising = change > 0
    good = rising if higher_is_better else not rising

    return (
        f'<span class="{GOOD if good else BAD}">'
        f'{"▲" if rising else "▼"} {abs(change):.{digits}f}</span>'
    )


def _movement(metrics, key, digits, higher_is_better=True):
    """
    The month-on-month line under a figure.

    Empty when there is no previous month in view - a single selected month
    has nothing to be compared against, and reaching outside the filter for
    one would report a number the user excluded. The slot is reserved in CSS
    either way, so the card keeps its height.
    """

    change = metrics.get(key)
    latest = metrics.get("latest_month")
    previous = metrics.get("previous_month")

    if change is None or latest is None or previous is None:
        return ""

    return _delta(change, digits, higher_is_better) + f" in {latest} vs {previous}"


def _lens_tile(name, accuracy, observations):
    """
    One lens: its score, its own meter against the same target tick, and how
    far off it is.

    The meter is the hero's, at a smaller size. Repeating the motif rather
    than inventing a second way of drawing the same comparison means the tile
    can be read without being explained.
    """

    gap = accuracy - ACCURACY_TARGET

    # Rounded before the test, so a lens that displays as exactly the target
    # is not labelled as below it by a difference too small to show.
    cleared = round(gap, 1) >= 0
    width = min(max(accuracy, 0), 100)

    return (
        f'<div class="lens-card">'
        f'<span class="lens-name" title="{lens_label(name)}">{lens_label(name)}</span>'
        f'<span class="lens-value">{accuracy:.1f}'
        f'<span class="lens-unit">%</span></span>'
        f'<div class="lens-meter">'
        f'<div class="lens-meter-fill" style="width:{width:.1f}%;"></div>'
        f'<div class="lens-meter-target" style="left:{ACCURACY_TARGET:g}%;"></div>'
        f"</div>"
        f'<span class="lens-foot">'
        f'<span class="{GOOD if cleared else BAD}">'
        f'{"▲" if cleared else "▼"} {abs(gap):.1f} pts</span>'
        f" · {int(observations)} readings</span>"
        f"</div>"
    )


def _lens_strip(metrics):
    """
    Accuracy per lens, as a row of small meters under the headline bar.

    Absent, not empty, when there is nothing to show - the unit filtered out
    of the view, or its rows carrying no lens. A row of zeroed tiles would
    read as "every lens scored nothing" rather than "lens does not apply to
    what is on screen".
    """

    scores = metrics.get("lens_scores")

    if scores is None or scores.empty:
        return ""

    tiles = "".join(
        _lens_tile(row.lens, row.accuracy, row.observations)
        for row in scores.itertuples()
    )

    return (
        f'<div class="lens-strip">'
        f'<p class="lens-strip-title">{metrics["lens_unit"]} accuracy by lens'
        f"<span>against the same {ACCURACY_TARGET:g}% target</span></p>"
        f'<div class="lens-grid">{tiles}</div>'
        f"</div>"
    )


def _hero(metrics):
    """Accuracy against target, as a figure and a bar with a target tick."""

    accuracy = metrics["overall_accuracy"]
    gap = accuracy - ACCURACY_TARGET

    # The figure above is the average across every month in view, so the
    # latest month is named separately rather than left to be inferred.
    movement = (
        f"{metrics['latest_month']} {metrics['latest_accuracy']:.1f}% "
        f"({_delta(metrics['accuracy_change'], 1)} pts "
        f"vs {metrics['previous_month']})"
        if metrics.get("accuracy_change") is not None
        else ""
    )

    direction = "below" if gap < 0 else "above"

    # One unbroken line, not an indented block. Streamlit reads the markup as
    # Markdown first, so an empty lens strip used to leave a blank line with
    # the indented tags under it - a code fence, printing the tags as text.
    return (
        f'<div class="hero">'
        f"<div>"
        f'<span class="hero-value">{accuracy:.2f}<span class="hero-unit">%</span></span>'
        f'<p class="hero-label">Average accuracy across this selection</p>'
        f"</div>"
        f"<div>"
        f'<p class="hero-gap"><span class="{BAD if gap < 0 else GOOD}">'
        f"{abs(gap):.2f} pts {direction}</span>"
        f" the {ACCURACY_TARGET:g}% target</p>"
        f'<div class="meter">'
        f'<div class="meter-fill" style="width:{min(max(accuracy, 0), 100):.2f}%;"></div>'
        f'<div class="meter-target" style="left:{ACCURACY_TARGET:g}%;"></div>'
        f"</div>"
        f'<p class="meter-scale"><span>0%</span><span>100%</span></p>'
        f"{_lens_strip(metrics)}"
        f'<p class="hero-move">{movement}</p>'
        f"</div>"
        f"</div>"
    )


def _badge(failing, total):
    """
    The card's reading in one chip: a mark, a colour and a wording.

    The design note at the top of style.css rules out an emoji on every
    heading - as decoration it carries nothing. This one is the card's
    verdict, so it changes with the figure beside it rather than sitting
    there whatever the data says. Colour never carries it alone; the wording
    is the same information.
    """

    if not failing:
        return '<span class="badge badge-ok">✅ Every category on target</span>'

    if total and failing / total >= WIDESPREAD:
        return '<span class="badge badge-bad">🚨 Most categories below target</span>'

    return '<span class="badge badge-warn">⚠️ Some categories below target</span>'


def _worst_preview(scores):
    """
    The few furthest below target, named on the card's face.

    The card grew tall once the hero gained its lens breakdown - the two are
    grid items and stretch together - and an empty middle read as a card with
    nothing to say. These are the rows someone opens the drill-down for, so
    the first of them are shown without the click.
    """

    if scores.empty:
        return ""

    shown = scores.head(PREVIEW_ROWS)

    rows = "".join(
        f"<div><span>{name}</span><b>{value:.1f}%</b></div>"
        for name, value in shown.items()
    )

    remaining = len(scores) - len(shown)
    more = (
        f'<p class="stat-more">+{remaining} more · click for the full list</p>'
        if remaining else ""
    )

    return (
        f'<div class="stat-worst">'
        f'<p class="stat-worst-title">Furthest below target</p>'
        f"{rows}{more}</div>"
    )


def _detail_rows(scores):
    """Name/value rows for the drill-down panel."""

    rows = "".join(
        f"<div><span>{name}</span><b>{value:.1f}%</b></div>"
        for name, value in scores.items()
    )
    return f'<p class="kpi-detail-title">Below target</p>{rows}'


def _alert(metrics):
    """How many categories are below target, and the list behind them."""

    failing = metrics["needs_improvement"]
    total = metrics["categories"]

    # Three blocks, matching the hero: badge and figure at the top, the worst
    # of them through the middle, movement at the bottom. justify-content
    # spreads them, so the two cards' last lines land on the same baseline.
    face = (
        f"<div>"
        f"{_badge(failing, total)}"
        f'<span class="stat-value">{failing}</span>'
        f'<p class="stat-label">of {total} categories below target</p>'
        f"</div>"
        f'{_worst_preview(metrics["bad_categories"])}'
        f'<p class="stat-note">'
        f'{_movement(metrics, "needs_improvement_change", 0, higher_is_better=False)}'
        f"</p>"
    )

    if not failing:
        return f'<div class="stat stat-ok">{face}</div>'

    return (
        f'<details class="stat stat-pop">'
        f"<summary>{face}</summary>"
        f'<div class="kpi-detail">{_detail_rows(metrics["bad_categories"])}</div>'
        f"</details>"
    )


def _strip(metrics):
    """What the current view covers. Inventory, so it is set quietly."""

    items = [
        (metrics["categories"], "categories"),
        (metrics["subcategories"], "subcategories"),
        (metrics["countries"], "countries"),
        (metrics["top_category"], "strongest category"),
    ]

    cells = "".join(
        f"<div><b>{value}</b><span>{label}</span></div>" for value, label in items
    )

    return f'<div class="strip">{cells}</div>'


def show_kpi_cards(metrics):

    # One grid, not two st.columns. A grid item stretches to the height of
    # the tallest by default; separate columns left the short card sitting at
    # its min-height while the hero grew well past it, so the two cards ended
    # at different depths.
    st.markdown(
        f'<div class="kpi-row">{_hero(metrics)}{_alert(metrics)}</div>',
        unsafe_allow_html=True,
    )

    st.markdown(_strip(metrics), unsafe_allow_html=True)
