from __future__ import annotations

import os

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from main import DEFAULT_TRACK_KEYWORDS

REFRESH_SECONDS = int(os.getenv("BUFF_UI_REFRESH_SEC", "900"))
CACHE_TTL_SECONDS = int(os.getenv("BUFF_UI_CACHE_TTL_SEC", "300"))
TRACK_KEYWORDS = tuple(DEFAULT_TRACK_KEYWORDS)
HIGH_VALUE_MIN_PRICE = float(os.getenv("BUFF_MIN_PRICE_CNY", "0"))


def configure_page() -> None:
    st.set_page_config(
        page_title="BUFF163 Price Analytics",
        page_icon="📈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st_autorefresh(interval=max(30, REFRESH_SECONDS) * 1000, key="buff_refresh")
