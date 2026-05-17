from __future__ import annotations

import os

SHEET_NAME = os.getenv("BUFF_SHEET_NAME", "BuffKnifeTracker")
LOG_SHEET_NAME = "HistoryLog"
CATALOG_SHEET_NAME = "Catalog"
ALL_CATALOG_SHEET_NAME = "AllCatalog"
DASHBOARD_SHEET_NAME = "Dashboard"
FORECAST_SHEET_NAME = "Forecast"
SIGNALS_SHEET_NAME = "Signals"

DEFAULT_BUTTERFLY_SEEDS = ["42552", "42555", "42533", "42587"]
DEFAULT_KARAMBIT_SEEDS = ["42901", "42905", "42911", "42909"]
DEFAULT_KNIFE_TYPES = [
    "Bayonet",
    "Bowie Knife",
    "Butterfly Knife",
    "Classic Knife",
    "Falchion Knife",
    "Flip Knife",
    "Gut Knife",
    "Huntsman Knife",
    "Karambit",
    "Kukri Knife",
    "M9 Bayonet",
    "Navaja Knife",
    "Nomad Knife",
    "Paracord Knife",
    "Shadow Daggers",
    "Skeleton Knife",
    "Stiletto Knife",
    "Survival Knife",
    "Talon Knife",
    "Ursus Knife",
]
DEFAULT_KNIFE_CATEGORIES = {
    "Bayonet": "weapon_bayonet",
    "Bowie Knife": "weapon_knife_survival_bowie",
    "Butterfly Knife": "weapon_knife_butterfly",
    "Classic Knife": "weapon_knife_css",
    "Falchion Knife": "weapon_knife_falchion",
    "Flip Knife": "weapon_knife_flip",
    "Gut Knife": "weapon_knife_gut",
    "Huntsman Knife": "weapon_knife_tactical",
    "Karambit": "weapon_knife_karambit",
    "Kukri Knife": "weapon_knife_kukri",
    "M9 Bayonet": "weapon_knife_m9_bayonet",
    "Navaja Knife": "weapon_knife_gypsy_jackknife",
    "Nomad Knife": "weapon_knife_outdoor",
    "Paracord Knife": "weapon_knife_cord",
    "Shadow Daggers": "weapon_knife_push",
    "Skeleton Knife": "weapon_knife_skeleton",
    "Stiletto Knife": "weapon_knife_stiletto",
    "Survival Knife": "weapon_knife_canis",
    "Talon Knife": "weapon_knife_widowmaker",
    "Ursus Knife": "weapon_knife_ursus",
}
DEFAULT_KNIFE_FINISHES = [
    "Doppler",
    "Gamma Doppler",
    "Marble Fade",
    "Fade",
    "Tiger Tooth",
    "Slaughter",
    "Crimson Web",
    "Case Hardened",
    "Blue Steel",
    "Damascus Steel",
    "Autotronic",
    "Lore",
    "Black Laminate",
    "Freehand",
    "Bright Water",
    "Ultraviolet",
    "Stained",
    "Vanilla",
]
DEFAULT_TRACK_KEYWORDS = DEFAULT_KNIFE_TYPES
DEFAULT_SQLITE_PATH = "buff163.sqlite3"

CSGOTRADER_BUFF_URL = "https://prices.csgotrader.app/latest/buff163.json"
CSGO_API_SKINS_URL = "https://raw.githubusercontent.com/ByMykel/CSGO-API/main/public/api/en/skins.json"
STEAM_IMAGE_CACHE_PATH = "steam_image_cache.json"

HISTORY_HEADERS = [
    "Timestamp",
    "Goods ID",
    "Family",
    "Knife Type",
    "Skin Name",
    "Condition",
    "Price",
    "Listings",
    "Buy Orders",
    "Reference Price",
    "Image URL",
    "Observed Orders",
]
CATALOG_HEADERS = [
    "Goods ID",
    "Family",
    "Skin Name",
    "Condition",
    "Price",
    "Listings",
    "Buy Orders",
    "Reference Price",
    "Image URL",
]
ALL_CATALOG_HEADERS = [
    "Timestamp",
    "Goods ID",
    "Family",
    "Skin Name",
    "Condition",
    "Price",
    "Listings",
    "Buy Orders",
    "Reference Price",
    "Image URL",
    "Goods URL",
]

CONDITION_ORDER = {
    "Factory New": 0,
    "Minimal Wear": 1,
    "Field-Tested": 2,
    "Well-Worn": 3,
    "Battle-Scarred": 4,
    "StatTrak": 5,
    "Unknown": 99,
}
