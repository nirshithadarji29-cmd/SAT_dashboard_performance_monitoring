from datetime import datetime

import streamlit as st

from config.settings import APP_NAME


def show_header(period=None):
    """
    `period` is what the loaded reports cover (see data_period).

    The card used to show today's date under the word "Updated", which reads
    as data freshness and is not - it changed every time the page was opened,
    whether or not a new report had arrived. The month the data runs through
    is the fact a reader is actually after; today's date stays as a smaller
    line so nothing is lost.
    """

    viewed = datetime.now().strftime("%d %b %Y")

    # Was 5:1. The right-hand card carries four lines now, and at one sixth
    # of the width they wrapped to six - leaving the two header blocks with
    # ragged bottoms. Both are flex columns of the same min-height in CSS.
    left, right = st.columns([3.2, 1])

    with left:
        st.markdown(
            f"""
        <div class="header">
            <h1>{APP_NAME}</h1>
            <p>Consumer intelligence quality, read monthly from OneDrive</p>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with right:

        period = period or {}

        span = period.get("span") or ""
        reports = period.get("reports") or 0

        st.markdown(
            f"""
        <div class="header">
            <p class="period-label">Data through</p>
            <p class="period-value">{period.get("latest") or "No data"}</p>
            <p class="period-detail">
                {span}<br>
                {reports} reports · viewed {viewed}
            </p>
        </div>
        """,
            unsafe_allow_html=True,
        )
