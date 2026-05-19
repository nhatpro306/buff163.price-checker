from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from src.dashboard.frames import choose_image_url


def base_knife_type(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("StatTrak"):
        return text.split(" ", 1)[1].strip() if " " in text else text
    return text

def knife_tile_image(frame: pd.DataFrame) -> str:
    priority = (
        "Doppler",
        "Gamma Doppler",
        "Marble Fade",
        "Fade",
        "Tiger Tooth",
        "Slaughter",
        "Crimson Web",
        "Case Hardened",
    )
    for finish in priority:
        image_url = choose_image_url(
            frame[frame["Family"].str.contains(finish, case=False, na=False)]
        )
        if image_url:
            return image_url
    return choose_image_url(frame.sort_values("Timestamp"))


def section_title(title: str, subtitle: str = "") -> None:
    st.markdown(
        f"""
        <div class="buff-section-title">
          <h3>{html.escape(title)}</h3>
          {f'<span>{html.escape(subtitle)}</span>' if subtitle else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(title: str, detail: str) -> None:
    st.markdown(
        f"""
        <div class="buff-empty">
          <strong>{html.escape(title)}</strong>
          <span>{html.escape(detail)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_market_table(frame: pd.DataFrame) -> pd.io.formats.style.Styler:
    visible = frame.copy()
    for col in ("Price", "Reference Price", "Predicted Price"):
        if col in visible.columns:
            visible[col] = pd.to_numeric(visible[col], errors="coerce")
    for col in ("Listings", "Buy Orders", "Observed Orders", "Predicted Listings"):
        if col in visible.columns:
            visible[col] = pd.to_numeric(visible[col], errors="coerce")
    formatters = {
        col: "{:,.2f} CNY"
        for col in ("Price", "Reference Price", "Predicted Price")
        if col in visible.columns
    }
    formatters.update(
        {
            col: "{:,.0f}"
            for col in ("Listings", "Buy Orders", "Observed Orders", "Predicted Listings")
            if col in visible.columns
        }
    )
    return visible.style.format(formatters, na_rep="N/A")
