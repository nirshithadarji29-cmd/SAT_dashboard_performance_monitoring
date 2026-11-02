from pathlib import Path

import plotly.express as px
import streamlit as st

from components.cards import show_kpi_cards
from components.filters import show_filters
from components.header import show_header
from components.leaders import show_leaders
from components.recommendations import show_recommendations
from components.summary import show_summary
from config.labels import map_location, unit_label
from config.settings import (
    ACCURACY_TARGET,
    APP_NAME,
    BG_DARK,
    DATA_CACHE_TTL,
    PANEL_DARK,
)
from scripts.loaders.read_s3 import (
    describe_data_problem,
    get_sat_root,
    load_all_data,
    refresh_data,
)
from scripts.metrics import calculate_metrics
from scripts.processors.dashboard_data import (
    category_accuracy,
    country_columns,
    data_period,
    subcategory_accuracy,
)
from scripts.processors.filter_data import apply_filters, selected_countries

st.set_page_config(
    page_title=APP_NAME,
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ---------------------------------------------------------------- rendering

@st.cache_data(ttl=DATA_CACHE_TTL, show_spinner=False)
def load_css(path):
    return Path(path).read_text(encoding="utf-8")


# Sequential ramps: one hue, light -> dark. A rainbow scale would imply
# categories where the data is really a magnitude.
SEQ_BLUE = ["#14375E", "#2F80ED", "#9BCBFF"]
SEQ_TEAL = ["#0E3B3B", "#1E9E8A", "#8FE3D0"]

# Categorical palette for business units. Colour here encodes *identity* -
# which unit a bar belongs to - so it needs distinct hues rather than a ramp.
#
# Validated against PANEL_DARK, the surface these charts render on: the first
# three slots clear every gate on the all-pairs list (worst colour-vision
# separation dE 9.4, normal vision 20.9, all above 3:1 contrast); five clear
# the adjacent list, which is what grouped bars are read on.
UNIT_PALETTE = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"]

# For any unit beyond the palette. Inventing more hues would produce colours
# indistinguishable from the existing ones for colourblind readers.
MUTED_INK = "#898781"

# Status red, for the one chart whose whole subject is failure. Deliberately
# not a slot from UNIT_PALETTE: a status colour that doubles as a series
# colour starts impersonating that series. Clears 3:1 on PANEL_DARK.
STATUS_CRITICAL = "#d03b3b"


# The face the page is set in, handed to Plotly so the charts do not render
# in a different one from the text around them.
CHART_FONT = (
    "Segoe UI Variable Text, Segoe UI, system-ui, -apple-system, sans-serif"
)


def style_chart(fig, height):
    """Apply the shared dark theme. Keeps all charts visually identical."""

    fig.update_layout(
        height=height,
        paper_bgcolor=BG_DARK,
        plot_bgcolor=PANEL_DARK,
        font=dict(color="white", size=13, family=CHART_FONT),
        # No figure titles anywhere: each chart sat under a Streamlit heading
        # that said the same thing, at a different indent - the section
        # heading at the page's padding, the figure title inside the
        # figure's own margin. The top margin drops with them.
        margin=dict(l=20, r=20, t=20, b=20),
        coloraxis_showscale=False,
        xaxis=dict(title="", gridcolor="rgba(255,255,255,.08)", zeroline=False),
        yaxis=dict(title="", gridcolor="rgba(255,255,255,.08)"),
    )
    return fig


def chart_title(text, note=None):
    """A heading for a chart that has no section heading of its own."""

    st.markdown(f'<p class="chart-title">{text}</p>', unsafe_allow_html=True)

    if note:
        st.markdown(f'<p class="chart-note">{note}</p>', unsafe_allow_html=True)


def target_line(fig):
    """A threshold, not a gridline - which is what the dash distinguishes."""

    fig.add_hline(
        y=ACCURACY_TARGET,
        line=dict(color="rgba(255,255,255,.55)", width=1, dash="dash"),
        annotation_text=f"Target {ACCURACY_TARGET:g}%",
        annotation_position="top right",
        annotation_font=dict(color="white", size=12),
    )
    return fig


def table_view(frame, label="View as table"):
    """The chart's exact equivalent, in numbers."""

    with st.expander(label):
        st.dataframe(frame, width="stretch")


def unit_color_map(*frames):
    """
    business_unit -> colour, fixed for the life of the session.

    Built from the UNFILTERED frames on purpose. Assigning colours to
    whichever units survive the current filter would repaint the survivors
    every time the filters move, so a reader who learned "retail is green"
    would be misled the moment they narrowed the view.

    Keyed by the displayed spelling, which is what the charts colour by.
    """

    units = sorted({
        unit_label(value)
        for frame in frames
        if frame is not None and "business_unit" in frame.columns
        for value in frame["business_unit"].dropna()
        if str(value).strip()
    })

    assigned = dict(zip(units, UNIT_PALETTE))

    return {unit: assigned.get(unit, MUTED_INK) for unit in units}


def accuracy_trend(scores, order, colors, scorecard, height=430):
    """
    Accuracy by month, one line per business unit.

    The single most-asked question of a monthly report - is it getting better?
    - and the one the dashboard could not answer while every figure was a
    blend of every month loaded.
    """

    if scores.empty or len(order) < 2:
        # The Month filter holds one month at a time, so a trend needs the
        # filter set back to "Overall" - that is the only selection that
        # leaves more than one month in the data.
        st.info('Set the Month filter to "Overall" to compare months.')
        return

    # category_orders puts the months in calendar order on the AXIS, but a
    # line is drawn through its points in the order the data arrives - and the
    # data arrives grouped, which is alphabetical. Without this the line
    # zigzags across the axis (April -> February -> January -> June).
    position = {month: index for index, month in enumerate(order)}
    data = (
        scores.assign(_month=scores["month"].map(position))
        .sort_values(["business_unit", "_month"])
        .drop(columns="_month")
    )

    # Direct labels on the last point only. Labelling every point on six
    # months x three units is 18 numbers competing with the lines they
    # describe; the last value is the one being read off.
    data["label"] = [
        f" {row.accuracy:.1f}%" if row.month == order[-1] else ""
        for row in data.itertuples()
    ]

    fig = px.line(
        data,
        x="month",
        y="accuracy",
        color="business_unit",
        text="label",
        markers=True,
        category_orders={"month": order, "business_unit": list(colors)},
        color_discrete_map=colors,
    )

    fig.update_traces(
        line=dict(width=2),
        marker=dict(size=9, line=dict(width=2, color=PANEL_DARK)),
        textposition="middle right",
        textfont=dict(color="white", size=12),
        cliponaxis=False,
        hovertemplate="%{fullData.name}: %{y:.1f}%<extra></extra>",
    )

    fig = style_chart(fig, height)

    # Lines encode position rather than length, so the axis does not have to
    # start at zero - and should not, or six months of movement inside a
    # 20-point band would flatten into one straight line. The target has to
    # stay inside the frame whatever the data does.
    low = min(data["accuracy"].min(), ACCURACY_TARGET)
    high = max(data["accuracy"].max(), ACCURACY_TARGET)
    pad = max((high - low) * 0.15, 2)

    fig.update_layout(
        # One shared crosshair rather than three separate hovers, so the
        # months can be compared across units at a glance.
        hovermode="x unified",
        margin_r=90,
        # Room for the legend, which sits above the plot area.
        margin_t=48,
        yaxis=dict(
            title="Accuracy (%)",
            range=[low - pad, high + pad],
            gridcolor="rgba(255,255,255,.08)",
        ),
        legend=dict(
            title="", orientation="h",
            yanchor="bottom", y=1.02, xanchor="left", x=0,
        ),
    )

    st.plotly_chart(target_line(fig), width="stretch")

    if not scorecard.empty:
        # Where each unit stands against the one target line, in numbers.
        # A single 85% is held up against all three, but retail has never
        # cleared 80% and Social has never dropped below 88% - the gap column
        # is what makes those different problems legible.
        st.caption(
            f"Where each business unit stands in {order[-1]}, against the "
            f"{ACCURACY_TARGET:g}% target."
        )
        st.dataframe(scorecard, width="stretch")


def accuracy_by_unit(scores, order, colors, height):
    """
    Grouped bars: one bar per business unit within each category.

    Replaces a single bar per category coloured by its own accuracy. That
    spent the colour channel restating the bar length, and averaging the
    units together hid the real spread - Social scores 94.9% on Alcoholic
    Beverage where Food Service scores 72.2%.
    """

    if scores.empty:
        st.info("No category accuracy data is available.")
        return

    fig = px.bar(
        scores,
        x="category",
        y="accuracy",
        color="business_unit",
        barmode="group",
        custom_data=["observations"],
        # Categories best-first; units in palette order, so the legend order
        # matches the colour assignment.
        category_orders={"category": order, "business_unit": list(colors)},
        color_discrete_map=colors,
    )

    # Up to 45 bars, so no value printed on every one - that reads as noise
    # and goes unread. The legend names the units, the axis and the hover
    # carry the values, and the table below is the exact equivalent.
    fig.update_traces(
        marker_cornerradius=4,
        hovertemplate=(
            "<b>%{x}</b><br>%{fullData.name}: %{y:.1f}%"
            "<br>%{customdata[0]} readings<extra></extra>"
        ),
    )

    # Applied after style_chart, which sets margin and both axes wholesale.
    # Category names are long, so angle them and leave room underneath.
    fig = style_chart(fig, height)
    fig.update_layout(
        bargap=0.28,       # between categories
        bargroupgap=0.08,  # the gap between bars inside one category
        xaxis_tickangle=-40,
        margin_b=150,
        # Room for the legend, which sits above the plot area.
        margin_t=48,
        # Bars encode length, so the axis has to start at zero. The full
        # 0-100 range keeps the scale stable as filters change.
        yaxis=dict(
            title="Accuracy (%)",
            range=[0, 100],
            gridcolor="rgba(255,255,255,.08)",
        ),
        legend=dict(
            title="",
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
        ),
    )

    st.plotly_chart(target_line(fig), width="stretch")

    # Every value stays reachable without hovering, with the reading count
    # beside it: a category scored from eight readings and one scored from
    # five hundred are indistinguishable on the chart.
    accuracy = (
        scores.pivot(index="category", columns="business_unit", values="accuracy")
        .reindex(order)
        .round(1)
    )
    readings = (
        scores.pivot(index="category", columns="business_unit", values="observations")
        .reindex(order)
        # Nullable ints: a unit with no rows for a category has no count, and
        # a plain int column cannot hold that gap.
        .astype("Int64")
        .add_suffix(" (n)")
    )

    table_view(accuracy.join(readings))


def accuracy_dots(scores, counts, label, height, color):
    """
    Dot plot for values packed into a narrow band.

    Dots encode position, not length, so the axis can start near the data
    instead of at zero - which is what makes a few points of difference
    visible. Doing the same to a bar chart would exaggerate the gaps.
    """

    if scores.empty:
        st.info(f"No {label} accuracy data is available.")
        return

    data = scores.sort_values().reset_index()
    data.columns = [label, "accuracy"]
    data["observations"] = [
        int(counts.get(name, 0)) for name in data[label]
    ]
    data["gap"] = (data["accuracy"] - ACCURACY_TARGET).round(1)

    fig = px.scatter(
        data, x="accuracy", y=label, text="accuracy",
        custom_data=["observations", "gap"],
    )
    fig.update_traces(
        marker=dict(size=15, color=color, line=dict(width=2, color=BG_DARK)),
        texttemplate="%{text:.1f}%",
        textposition="middle right",
        textfont_color="white",
        cliponaxis=False,
        hovertemplate=(
            "<b>%{y}</b><br>%{x:.1f}% (%{customdata[1]:+.1f} vs target)"
            "<br>%{customdata[0]} readings<extra></extra>"
        ),
    )

    fig = style_chart(fig, height)
    low, high = data["accuracy"].min(), data["accuracy"].max()
    pad = max((high - low) * 0.25, 1)
    fig.update_layout(
        # These two charts sit side by side in half-width columns, where a
        # 220px label gutter left almost nothing for the dots themselves.
        margin_l=150,
        margin_r=64,
        xaxis=dict(
            range=[low - pad, high + pad],
            gridcolor="rgba(255,255,255,.08)",
            title="",
        ),
        yaxis=dict(showgrid=False, title=""),
    )

    st.plotly_chart(fig, width="stretch")

    table = data.set_index(label).rename(columns={
        "accuracy": "Accuracy (%)",
        "observations": "Readings",
        "gap": "Gap to target (pts)",
    }).round(1)

    table_view(table)


# ------------------------------------------------------------------- styles

css_path = Path(__file__).parent / "assets" / "style.css"

if css_path.exists():
    st.markdown(f"<style>{load_css(css_path)}</style>", unsafe_allow_html=True)
else:
    st.warning("CSS file not found. Please check assets/style.css")


# --------------------------------------------------------------------- data

sat_root = get_sat_root()
category_df, subcategory_df = load_all_data(sat_root)

if category_df.empty or subcategory_df.empty:

    st.error(
        "Could not locate the SAT data folder on this machine."
        if sat_root is None
        else f"Found the SAT data folder at `{sat_root}`, but no usable "
             "Category and Subcategory reports were read from it."
    )

    with st.expander("Details", expanded=True):
        st.code(describe_data_problem(sat_root))

    if st.button("Retry"):
        refresh_data()
        st.rerun()

    st.stop()


# Assigned from the unfiltered data, so a business unit keeps the same colour
# whatever the filters are set to.
unit_colors = unit_color_map(category_df, subcategory_df)


show_header(data_period(category_df, subcategory_df))

# Centred, so the caption sits on the button's midline instead of floating at
# the top of a row the button makes taller.
source_col, refresh_col = st.columns([6, 1], vertical_alignment="center")

with source_col:
    st.caption(f"Data source: `{sat_root}`")

with refresh_col:
    if st.button("Refresh data", width="stretch"):
        refresh_data()
        st.rerun()


# ------------------------------------------------------------------ filters

filters = show_filters(category_df, subcategory_df)

filtered_category_df, filtered_subcategory_df = apply_filters(
    category_df, subcategory_df, filters
)

# Melt only the selected country rather than all of them and discarding the
# rest afterwards.
countries = selected_countries(
    filters, country_columns(filtered_category_df, filtered_subcategory_df)
)

category_long = category_accuracy(filtered_category_df, countries)
subcategory_long = subcategory_accuracy(filtered_subcategory_df, countries)

if category_long.empty or subcategory_long.empty:
    st.warning("No SAT data is available for the selected filters.")
    st.stop()


# ------------------------------------------------------------------ metrics

metrics = calculate_metrics(category_long, subcategory_long)

show_kpi_cards(metrics)
# Above the summary rather than below the charts: it is the answer to the
# question customers ask first, and the summary reads as a comment on it.
show_leaders(metrics)
# The summary describes the filtered view, so it needs to know what was
# filtered - the numbers alone cannot say whether "1 country" means one was
# selected or only one had data.
show_summary(metrics, filters)

# ------------------------------------------------------------------- charts
# Section spacing is a margin on the headings themselves now, so it is the
# same everywhere instead of a divider in one place and nothing in the rest.

st.subheader("Accuracy by month")
accuracy_trend(
    metrics["unit_month_scores"],
    metrics["months"],
    unit_colors,
    metrics["unit_scorecard"],
)

st.subheader("Category accuracy by business unit")
accuracy_by_unit(
    metrics["category_unit_scores"],
    # category_scores is already sorted best-first.
    list(metrics["category_scores"].index),
    unit_colors,
    height=560,
)

st.subheader("Strongest and weakest subcategories")

best_col, worst_col = st.columns(2)

with best_col:
    chart_title("Strongest 10")
    accuracy_dots(
        metrics["subcategory_scores"].head(10),
        metrics["subcategory_counts"],
        "subcategory",
        height=460,
        color=SEQ_TEAL[1],
    )

with worst_col:
    # The half of the ranking a decision is actually made from. Ordered by
    # score, which for anything under the target is the same order as by gap
    # to it.
    chart_title("Weakest 10")
    accuracy_dots(
        metrics["subcategory_scores"].tail(10),
        metrics["subcategory_counts"],
        "subcategory",
        height=460,
        color=STATUS_CRITICAL,
    )

st.caption(
    "A 0.0% reading means the report carried a zero for that country, which "
    "is not always the same as a measured score of zero."
)

st.subheader("Accuracy by country")

country_scores = metrics["country_scores"].reset_index()
country_scores.columns = ["country", "accuracy"]

if country_scores.empty:
    st.info("No country-level accuracy data is available.")
else:
    country_scores["observations"] = [
        int(metrics["country_counts"].get(name, 0))
        for name in country_scores["country"]
    ]
    # Plotted under the name Plotly knows; labelled with the report's own.
    country_scores["location"] = country_scores["country"].map(map_location)

    fig = px.choropleth(
        country_scores,
        locations="location",
        locationmode="country names",
        color="accuracy",
        hover_name="country",
        custom_data=["observations"],
        color_continuous_scale=SEQ_BLUE,
    )
    fig = style_chart(fig, 650)
    # Coverage is very uneven - hundreds of readings for some countries and
    # tens for others - and the map gives them all the same visual weight, so
    # the count travels with the value.
    fig.update_traces(
        hovertemplate=(
            "<b>%{hovertext}</b><br>%{z:.1f}%"
            "<br>%{customdata[0]} readings<extra></extra>"
        )
    )
    # The map has no direct labels, so it keeps its colour scale. Its margins
    # match every other figure - at l=0 the map's panel edge stuck out past
    # the charts above it.
    fig.update_layout(coloraxis_showscale=True, margin=dict(l=20, r=20, t=10, b=10))
    # projection_scale fills the box without locking the view. Setting
    # lataxis/lonaxis ranges here would freeze the projection and disable
    # zooming altogether.
    fig.update_geos(
        bgcolor=PANEL_DARK,
        showframe=False,
        # Countries with no data still need to be drawn, otherwise the ones
        # that do have data float in empty space.
        showland=True,
        landcolor="#1B3450",
        showocean=True,
        oceancolor=PANEL_DARK,
        lakecolor=PANEL_DARK,
        showcoastlines=True,
        coastlinecolor="rgba(255,255,255,.22)",
        showcountries=True,
        countrycolor="rgba(255,255,255,.14)",
        projection_scale=1,
    )

    # Plotly's geo subplot has no minimum-zoom setting, so zoom-out is removed
    # rather than clamped: the map can never shrink below the fitted view.
    # Zoom-in (+ button, double-click) and reset stay available.
    st.plotly_chart(
        fig,
        width="stretch",
        config={
            "scrollZoom": False,
            "modeBarButtonsToRemove": ["zoomOutGeo"],
            "displaylogo": False,
            "doubleClick": "reset",
        },
    )

    table = (
        country_scores
        .set_index("country")[["accuracy", "observations"]]
        .rename(columns={"accuracy": "Accuracy (%)", "observations": "Readings"})
        .round(1)
    )
    table_view(table)


# --------------------------------------------------------- recommendations

show_recommendations(metrics)
