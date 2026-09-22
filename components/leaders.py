"""
Strongest country x category pairs, ranked within each region.

The question this answers is the one customers ask by name - "which are your
strongest markets?" - and the page could not answer it: it named the best
*category* averaged over every country, which is not a market at all.

Each region is its own leaderboard rather than a slice of a combined one. On
a single global list the highest-scoring region takes most of the places and
everyone else is left with one entry, which is no use to someone who only
covers Europe.
"""

import streamlit as st

from config.settings import ACCURACY_TARGET
from scripts.metrics import LEADERS_PER_REGION

# Ranks marked on the face of a region's list: the leader filled, the two
# behind it tinted. Past three the mark stops distinguishing anything - a
# medal on every row is a medal on nothing.
MEDALS = 3


def _row(leader):
    """One pair: its rank in this region, the market, the score, the backing."""

    rank = leader["rank"]

    if rank == 1:
        mark = " leader-rank-first"
    elif rank <= MEDALS:
        mark = " leader-rank-top"
    else:
        mark = ""

    return (
        f'<div class="leader-row">'
        f'<span class="leader-rank{mark}">{rank}</span>'
        f'<span class="leader-name">{leader["country"]}'
        f'<span>{leader["category"]}</span></span>'
        f'<span class="leader-score">{leader["accuracy"]:.1f}'
        f'<span class="leader-unit">%</span>'
        f'<span class="leader-obs">{leader["observations"]} readings</span>'
        f"</span>"
        f"</div>"
    )


def _region(block):
    """One region's list, headed by how much of the region it covers."""

    leaders = block["leaders"]
    total = block["total"]

    # A region with fewer pairs than the cut-off is not a top ten, and saying
    # so is the difference between "these are the best ten" and "this is all
    # of them".
    covered = (
        f"top {len(leaders)} of {total}"
        if total > len(leaders)
        else f"all {total}"
    )

    rows = "".join(_row(leader) for leader in leaders)

    return (
        f'<div class="leader-region">'
        f'<p class="leader-region-title">{block["region"]}'
        f"<span>{covered}</span></p>"
        f"{rows}</div>"
    )


def show_leaders(metrics):

    regions = metrics.get("regional_leaders") or []

    st.subheader("Strongest markets by region")

    if not regions:
        st.info("No country-level accuracy data is available for this selection.")
        return

    st.markdown(
        f'<div class="section leaders">'
        f'<p class="leaders-note">The strongest {LEADERS_PER_REGION} country '
        f"and category pairs in each region, best first, against the "
        f"{ACCURACY_TARGET:g}% target. Regions are ordered by their own best "
        f"score.</p>"
        f'<div class="leader-grid">'
        f'{"".join(_region(block) for block in regions)}'
        f"</div></div>",
        unsafe_allow_html=True,
    )
