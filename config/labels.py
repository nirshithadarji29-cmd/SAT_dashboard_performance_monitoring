"""
How raw values are spelled on screen.

The reports' own spellings are what the filters match on, so nothing here
rewrites a value in the data - these functions are applied at the moment a
value is displayed. Keeping the two apart means a prettier label can never
change which rows a filter selects.

A leaf module, like config/settings.py: it imports nothing from the app.
"""

# Business unit is resolved per row by the loader, from two sources with two
# spelling conventions: the folder name ("Social") and the product_type column
# ("food_service", "retail"). Anything not listed falls back to the generic
# rule below.
UNIT_DISPLAY_NAMES = {
    "food_service": "Food Service",
    "retail": "Retail",
    "social": "Social",
}

# Rows the reports carry as their own per-category aggregate rather than as a
# real subcategory. Ranking one of these beside genuine subcategories would
# put a summary row in a Top or Bottom 10.
AGGREGATE_LABELS = {"all", "total", "overall"}

# Plotly matches choropleth locations against a fixed list of country names.
# The reports use a short or formal name for these four, which that list does
# not carry, so they would silently fail to draw. Mapped for the map's
# `locations` only - the name the reader sees stays the report's own.
MAP_COUNTRY_NAMES = {
    "Kingdom of Saudi Arabia": "Saudi Arabia",
    "UAE": "United Arab Emirates",
    "UK": "United Kingdom",
    "USA": "United States",
}


# Country -> region, for the "strongest by region" leaderboard.
#
# A hand-kept table rather than a geo library: the app reads local Excel and
# has no network at runtime, and the reports use their own short names ("UK",
# "USA", "Kingdom of Saudi Arabia") that a lookup keyed on ISO codes would
# miss anyway. Matching is case-insensitive on the stripped name.
#
# Deliberately wider than the 28 countries currently in the reports, so a
# country added next month lands in its region instead of in "Other".
COUNTRY_REGIONS = {
    # --- Asia Pacific
    "australia": "Asia Pacific",
    "bangladesh": "Asia Pacific",
    "china": "Asia Pacific",
    "hong kong": "Asia Pacific",
    "india": "Asia Pacific",
    "indonesia": "Asia Pacific",
    "japan": "Asia Pacific",
    "malaysia": "Asia Pacific",
    "new zealand": "Asia Pacific",
    "pakistan": "Asia Pacific",
    "philippines": "Asia Pacific",
    "singapore": "Asia Pacific",
    "south korea": "Asia Pacific",
    "sri lanka": "Asia Pacific",
    "taiwan": "Asia Pacific",
    "thailand": "Asia Pacific",
    "vietnam": "Asia Pacific",

    # --- Europe
    "austria": "Europe",
    "belgium": "Europe",
    "czech republic": "Europe",
    "denmark": "Europe",
    "finland": "Europe",
    "france": "Europe",
    "germany": "Europe",
    "greece": "Europe",
    "hungary": "Europe",
    "ireland": "Europe",
    "italy": "Europe",
    "netherlands": "Europe",
    "norway": "Europe",
    "poland": "Europe",
    "portugal": "Europe",
    "romania": "Europe",
    "russia": "Europe",
    "spain": "Europe",
    "sweden": "Europe",
    "switzerland": "Europe",
    "turkey": "Europe",
    "uk": "Europe",
    "ukraine": "Europe",
    "united kingdom": "Europe",

    # --- Americas
    "argentina": "Americas",
    "brazil": "Americas",
    "canada": "Americas",
    "chile": "Americas",
    "colombia": "Americas",
    "mexico": "Americas",
    "peru": "Americas",
    "usa": "Americas",
    "united states": "Americas",
    "united states of america": "Americas",

    # --- Middle East & Africa
    "algeria": "Middle East & Africa",
    "egypt": "Middle East & Africa",
    "ghana": "Middle East & Africa",
    "israel": "Middle East & Africa",
    "kenya": "Middle East & Africa",
    "kingdom of saudi arabia": "Middle East & Africa",
    "kuwait": "Middle East & Africa",
    "morocco": "Middle East & Africa",
    "nigeria": "Middle East & Africa",
    "qatar": "Middle East & Africa",
    "saudi arabia": "Middle East & Africa",
    "south africa": "Middle East & Africa",
    "tanzania": "Middle East & Africa",
    "uae": "Middle East & Africa",
    "united arab emirates": "Middle East & Africa",
}

# Where a country the table does not carry is filed. Named rather than dropped:
# a leaderboard that silently omits a country is worse than one that admits it
# does not know where to put it.
OTHER_REGION = "Other"


def region_of(country):
    """"UK" -> "Europe". Unknown names fall back to OTHER_REGION."""

    return COUNTRY_REGIONS.get(str(country).strip().lower(), OTHER_REGION)


def unit_label(value):
    """"food_service" -> "Food Service". Display only."""

    text = str(value).strip()

    if not text:
        return text

    # Applied only to business units: a general title-casing rule would damage
    # the other columns ("Ready-to-Eat" -> "Ready-To-Eat", "UK" -> "Uk").
    return UNIT_DISPLAY_NAMES.get(text.lower(), text.replace("_", " ").title())


def lens_label(value):
    """"product_attribute" -> "Product Attribute". Display only."""

    text = str(value).strip()

    # Lens values are plain lowercase words joined by underscores, so unlike
    # the category names a general title-casing rule is safe here.
    return text.replace("_", " ").title()


def is_aggregate(value):
    """True for a report's own summary row, e.g. subcategory "All"."""

    return str(value).strip().lower() in AGGREGATE_LABELS


def map_location(country):
    """The name Plotly knows this country by."""

    text = str(country).strip()

    return MAP_COUNTRY_NAMES.get(text, text)
