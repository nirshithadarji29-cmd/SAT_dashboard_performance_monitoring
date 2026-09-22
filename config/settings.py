"""
Shared constants. This module is a leaf: it imports nothing from the app, so
every other package can depend on it without creating an import cycle.

Values that can be derived from the reports themselves are NOT listed here -
see scripts/processors/dashboard_data.py (country columns) and
components/filters.py (month ordering).
"""

import os

APP_NAME = "SAT Intelligence Platform"

# Accuracy target. Categories and subcategories below this need improvement.
# Cannot be derived from the data - it is a business decision.
ACCURACY_TARGET = float(os.getenv("SAT_ACCURACY_TARGET", "85"))

# How long loaded Excel data is cached before being re-read, in seconds.
DATA_CACHE_TTL = int(os.getenv("SAT_CACHE_TTL", "3600"))

# Sentinel used by every filter dropdown to mean "do not filter".
ALL_OPTION = "Overall"

# Where the SAT data folder lives.
#
# SAT_FOLDER_PATTERN is a "contains" pattern, not a prefix: OneDrive renames a
# folder shared with you via "Add shortcut to My files" to
#   "<Owner>'s files - Monthly_SAT_2026"
# so anchoring at the start of the name never matches a shared folder.
SAT_FOLDER_PATTERN = os.getenv("SAT_FOLDER_PATTERN", "*Monthly_SAT*")
SAT_DATA_ROOT = os.getenv("SAT_DATA_ROOT")
MAX_SEARCH_DEPTH = 3

# Structural columns of a report. Every OTHER column is a country, so the
# country list is derived from the data instead of being maintained by hand -
# a new country in the reports appears automatically.
NON_COUNTRY_COLUMNS = {
    "category",
    "subcategory",
    "product_type",
    "business_unit",
    "lens",
    "source",
    "month",
    "file_name",
}

# Reports spell the lens column inconsistently. In preference order: the
# loader coalesces these into one `lens` column per row (see _lens). Read
# this list ONLY when resolving a raw report; everything downstream reads
# LENS_COLUMN, which is guaranteed to exist and to be merged.
LENS_COLUMNS = ["lens", "Lens"]

# The one lens column the app filters, groups and charts on.
LENS_COLUMN = "lens"

# Lens values are merged down to the three the business reports on:
# ingredient, product and theme.
#
# The FS / Retail reports began scoring five dimensions in June against the
# same categories as the other three, so these are parallel measures rather
# than a finer breakdown of one. Folding them in keeps one vocabulary across
# both sources instead of a list of eight that cannot be compared.
#
# Keys are the reports' own lowercase spelling; a value not listed here is
# already canonical and passes through untouched.
LENS_MERGES = {
    "consumption_context": "theme",
    "product_attribute": "product",
    "culinary": "product",
}

# The business unit the per-lens breakdown on the hero card is reported for.
# Named here rather than in the view so there is one place to change it if
# another unit's lens becomes worth showing alongside.
LENS_UNIT = "Social"

# Subcategory lives only in the Subcategory reports. Listed as candidates for
# the same reason as LENS_COLUMNS: the casing is not guaranteed to stay
# consistent across months and sources.
SUBCATEGORY_COLUMNS = ["subcategory", "Subcategory"]

# Business unit is resolved per row by the loader: product_type when the
# report has one, otherwise the report's folder. See _business_unit().
#
# product_type is listed as a fallback for frames that predate that column
# (e.g. a cache written by an older build); its values are a subset of
# business_unit's, so including it never adds new options. "Source" is
# deliberately absent - it would reintroduce the combined "FS_Retail".
BUSINESS_UNIT_COLUMNS = ["business_unit", "product_type"]

# Chart palette, kept in step with assets/style.css.
BG_DARK = "#081A2F"
PANEL_DARK = "#102943"
