from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from main import CONDITION_ORDER, DEFAULT_TRACK_KEYWORDS


@dataclass(frozen=True)
class SidebarSelection:
    selected_knife_type: str
    family_selected: str
    condition_selected: str
    date_range: Any
    family_df: pd.DataFrame


def render_sidebar(history_df: pd.DataFrame, family_names: list[str]) -> SidebarSelection:
    knife_counts = history_df.groupby("_Base Knife")["Family"].nunique().sort_index()
    knife_types = [knife for knife in DEFAULT_TRACK_KEYWORDS if knife in knife_counts.index]

    with st.sidebar:
        st.markdown(
            """
            <div class="buff-sidebar-head">
              <strong>BUFF163 Analytics</strong>
              <span>Market filters and refresh controls</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        selected_knife_type = st.selectbox(
            "Knife",
            knife_types,
            index=0,
            format_func=lambda value: f"{value} ({int(knife_counts.get(value, 0))})",
        )
        scoped_names = sorted(
            history_df.loc[history_df["_Base Knife"] == selected_knife_type, "Family"]
            .dropna()
            .unique()
            .tolist()
        )
        filtered_families = scoped_names or family_names
        latest_family = (
            history_df[history_df["Family"].isin(filtered_families)]
            .sort_values("Timestamp")
            .groupby("Family", as_index=False)
            .tail(1)[["Family", "Price", "Listings"]]
        )
        sort_option = st.selectbox(
            "Sort",
            ("Name A-Z", "Latest price high-low", "Latest price low-high", "Listings high-low"),
        )
        if sort_option == "Latest price high-low":
            filtered_families = latest_family.sort_values("Price", ascending=False)[
                "Family"
            ].tolist()
        elif sort_option == "Latest price low-high":
            filtered_families = latest_family.sort_values("Price", ascending=True)[
                "Family"
            ].tolist()
        elif sort_option == "Listings high-low":
            filtered_families = latest_family.sort_values("Listings", ascending=False)[
                "Family"
            ].tolist()

        family_selected = st.selectbox(
            "Skin family", filtered_families, placeholder=f"{selected_knife_type} skins"
        )

    family_df = history_df[history_df["Family"] == family_selected].copy()
    condition_latest = (
        family_df.sort_values("Timestamp")
        .assign(
            _source_key=lambda frame: frame.get("Source", pd.Series("", index=frame.index))
            .eq("Fallback")
            .astype(int)
        )
        .sort_values(["_source_key", "Timestamp"])
        .groupby("Condition", as_index=False)
        .tail(1)
        .assign(
            _sort_key=lambda frame: frame["Condition"].map(
                lambda value: CONDITION_ORDER.get(str(value), 50)
            )
        )
        .sort_values(["_sort_key", "Condition"])
    )
    condition_labels = [
        f"{row['Condition'] or 'Unknown'}  {float(row['Price']):,.2f} CNY"
        for _, row in condition_latest.iterrows()
    ]
    condition_map = dict(zip(condition_labels, condition_latest["Condition"].tolist()))

    with st.sidebar:
        selected_condition_label = st.selectbox("Condition", condition_labels)
        min_day = family_df["Timestamp"].min().date()
        max_day = family_df["Timestamp"].max().date()
        date_range = st.date_input(
            "Date range", (min_day, max_day), min_value=min_day, max_value=max_day
        )
        if st.button("Refresh data", width="stretch"):
            st.cache_data.clear()
            st.rerun()

    return SidebarSelection(
        selected_knife_type=str(selected_knife_type),
        family_selected=str(family_selected),
        condition_selected=str(condition_map[selected_condition_label]),
        date_range=date_range,
        family_df=family_df,
    )
