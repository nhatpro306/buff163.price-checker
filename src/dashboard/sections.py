from __future__ import annotations

from collections.abc import Callable

import altair as alt
import pandas as pd
import streamlit as st

from src.dashboard.charts import chart_surface, daily_market_frame, price_history_chart
from src.dashboard.metrics import dashboard_kpis, market_signal_cards, top_movers
from src.dashboard.ui import empty_state, format_market_table, section_title
from main import FORECAST_SHEET_NAME


def render_hero(
    *,
    family_label: str,
    condition_label: str,
    knife_label: str,
    goods_id_label: str,
    last_update_label: str,
    live_checked_label: str,
    status_class: str,
    live_status_label: str,
    image_html: str,
    latest_price_label: str,
    average_price_label: str,
    highest_price_label: str,
    lowest_price_label: str,
    sell_stock_label: str,
    reference_price_label: str,
    buy_orders_label: str,
    listing_source: str,
    refresh_minutes: int,
) -> None:
    st.markdown(
        f"""
        <div class="buff-header">
          <div>
            <h1>BUFF163 Market Console</h1>
            <p>{family_label} | {condition_label} | {knife_label} | Goods ID {goods_id_label}</p>
            <p class="dash-tagline">AI-assisted CS2 skin market analytics with price history, liquidity signals, forecast tracking, and trend detection.</p>
            <p>Last update: {last_update_label} | Checked: {live_checked_label} | Auto refresh: {refresh_minutes} min</p>
          </div>
          <div class="buff-status{status_class}">Market {live_status_label}</div>
        </div>
        <div class="buff-hero">
          <div class="buff-grid">
            <div class="buff-image-card">
              {image_html}
            </div>
            <div class="buff-item-main">
              <div class="buff-market-tags">
                <span>CS2</span><span>{knife_label}</span><span>{condition_label}</span>
              </div>
              <h1 class="buff-title">{family_label}</h1>
              <div class="buff-market-tabs"><span>Selling</span><span>Buy Orders</span><span>History</span></div>
            </div>
            <div class="buff-price-panel">
              <div class="buff-price-label">Lowest sell order</div>
              <div class="buff-price-value">{latest_price_label}</div>
              <div class="buff-price-micro">
                <span>Average<strong>{average_price_label}</strong></span>
                <span>High<strong>{highest_price_label}</strong></span>
                <span>Low<strong>{lowest_price_label}</strong></span>
                <span>Listings<strong>{sell_stock_label}</strong></span>
              </div>
              <div class="buff-price-row"><span>Reference</span><strong>{reference_price_label}</strong></div>
              <div class="buff-price-row"><span>Buy orders</span><strong>{buy_orders_label}</strong></div>
              <div class="buff-price-row"><span>Source</span><strong>{listing_source}</strong></div>
              <div class="buff-price-row"><span>Updated</span><strong>{last_update_label}</strong></div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_kpis(analysis_df: pd.DataFrame, sell_stock: int) -> None:
    st.markdown(
        f'<div class="dash-kpi-grid">{dashboard_kpis(analysis_df, sell_stock)}</div>',
        unsafe_allow_html=True,
    )


def render_price_history_and_activity(
    analysis_df: pd.DataFrame, sell_stock: int, buy_orders: int
) -> None:
    daily_df = daily_market_frame(analysis_df)
    combined_chart = price_history_chart(daily_df)
    summary = (
        analysis_df[["Timestamp", "Price", "Listings", "Buy Orders"]]
        .sort_values("Timestamp", ascending=False)
        .head(8)
        .copy()
    )
    summary["Listings"] = summary["Listings"].fillna(0).astype(int)
    summary["Buy Orders"] = summary["Buy Orders"].fillna(0).astype(int)
    summary["Timestamp"] = summary["Timestamp"].dt.strftime("%Y-%m-%d %H:%M")

    chart_col, activity_col = st.columns((2.1, 1))
    with chart_col:
        section_title("Price History", "Daily average, 7-day moving average, and liquidity overlay")
        st.markdown('<div class="chart-shell">', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="chart-legend">
              <span><i class="legend-price"></i>Price</span>
              <span><i class="legend-ma"></i>7D MA</span>
              <span><i class="legend-stock"></i>Sell stock</span>
              <span><i class="legend-high"></i>High point</span>
              <span><i class="legend-low"></i>Low point</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.altair_chart(chart_surface(combined_chart), width="stretch")
        st.markdown("</div>", unsafe_allow_html=True)

    with activity_col:
        section_title("Market Activity", "Liquidity, trend, and smart signals")
        st.markdown(
            f'<div class="signal-grid">{market_signal_cards(analysis_df, sell_stock, buy_orders)}</div>',
            unsafe_allow_html=True,
        )
        section_title("Recent Listings", "Latest observed sell / buy depth")
        st.dataframe(format_market_table(summary), width="stretch", hide_index=True)


def render_forecast(
    forecast_df: pd.DataFrame,
    *,
    family_selected: str,
    condition_selected: str,
    load_sheet_records: Callable[[str], pd.DataFrame],
) -> None:
    section_title("AI Forecast", "Model-driven projection using the forecast sheet")
    if forecast_df.empty:
        with st.spinner("Loading forecast..."):
            forecast_df = load_sheet_records(FORECAST_SHEET_NAME)
    if forecast_df.empty:
        empty_state(
            "Forecast unavailable", "Forecast rows will appear here after the forecast job runs."
        )
        return

    forecast_df["Forecast Date"] = pd.to_datetime(forecast_df["Forecast Date"], errors="coerce")
    forecast_df["Predicted Price"] = pd.to_numeric(
        forecast_df.get("Predicted Price"), errors="coerce"
    )
    if "Predicted Listings" in forecast_df.columns:
        forecast_df["Predicted Listings"] = pd.to_numeric(
            forecast_df.get("Predicted Listings"), errors="coerce"
        )
    target_skin_name = f"{family_selected} ({condition_selected})"
    forecast_view = forecast_df[forecast_df["Skin Name"] == target_skin_name].dropna(
        subset=["Forecast Date", "Predicted Price"]
    )
    if forecast_view.empty:
        empty_state(
            "No forecast rows for this condition",
            "Choose another condition or refresh after forecasting completes.",
        )
        return

    forecast_chart = (
        alt.Chart(forecast_view)
        .mark_line(point=True, color="#61d394", interpolate="monotone", strokeWidth=3)
        .encode(
            x=alt.X("Forecast Date:T", title="Date"),
            y=alt.Y(
                "Predicted Price:Q",
                title="Predicted Price (CNY)",
                scale=alt.Scale(zero=False),
            ),
            tooltip=[
                alt.Tooltip("Forecast Date:T", title="Date"),
                alt.Tooltip("Predicted Price:Q", title="Predicted Price", format=",.2f"),
                alt.Tooltip("Model:N", title="Model"),
            ],
        )
        .properties(height=280)
    )
    st.altair_chart(chart_surface(forecast_chart), width="stretch")


def render_top_movers(history_df: pd.DataFrame, selected_knife_type: str) -> None:
    section_title("Top Movers / Trending Skins", "Largest recent price moves in the selected market")
    movers = top_movers(history_df[history_df["_Base Knife"] == selected_knife_type])
    if movers.empty:
        empty_state("No movers yet", "More historical points are needed to rank trending skins.")
        return

    movers_table = movers.copy()
    movers_table["Latest Price"] = movers_table["Latest Price"].map(
        lambda value: f"{value:,.2f} CNY"
    )
    movers_table["Change %"] = movers_table["Change %"].map(lambda value: f"{value:+.2f}%")
    movers_table["Listings"] = (
        pd.to_numeric(movers_table["Listings"], errors="coerce").fillna(0).astype(int)
    )
    st.dataframe(movers_table, width="stretch", hide_index=True)


def render_recent_listings(analysis_df: pd.DataFrame) -> None:
    section_title("Recent Listings Table", "Filtered historical observations")
    sell_view = analysis_df[
        ["Timestamp", "Price", "Listings", "Buy Orders", "Reference Price", "Observed Orders"]
    ].sort_values("Timestamp", ascending=False)
    if sell_view.empty:
        empty_state("No sell history", "Try widening the date range in the sidebar.")
        return

    sell_view["Listings"] = sell_view["Listings"].fillna(0).astype(int)
    sell_view["Buy Orders"] = sell_view["Buy Orders"].fillna(0).astype(int)
    sell_view["Observed Orders"] = (
        pd.to_numeric(sell_view["Observed Orders"], errors="coerce").fillna(0).astype(int)
    )
    st.dataframe(format_market_table(sell_view.head(25)), width="stretch", hide_index=True)
