from __future__ import annotations

import altair as alt
import pandas as pd

CHART_BACKGROUND = "#111a28"


def chart_surface(
    chart: alt.Chart | alt.LayerChart | alt.VConcatChart,
) -> alt.Chart | alt.LayerChart | alt.VConcatChart:
    return chart.configure(background=CHART_BACKGROUND).configure_view(
        fill=CHART_BACKGROUND,
        stroke="transparent",
    )


def daily_market_frame(frame: pd.DataFrame) -> pd.DataFrame:
    daily = frame.copy()
    if "Listings" in daily.columns:
        daily.loc[daily["Listings"].fillna(0) <= 0, "Listings"] = pd.NA
    daily["Day"] = daily["Timestamp"].dt.date
    daily = daily.groupby("Day", as_index=False).agg(
        Price=("Price", "mean"),
        Listings=("Listings", "last"),
        BuyOrders=("Buy Orders", "last"),
    )
    daily["Day"] = pd.to_datetime(daily["Day"])
    daily["Moving Average"] = daily["Price"].rolling(7, min_periods=1).mean()
    daily["ListingsChart"] = pd.to_numeric(daily["Listings"], errors="coerce").fillna(0)
    return daily


def price_history_chart(daily: pd.DataFrame) -> alt.LayerChart:
    high_point = daily[daily["Price"] == daily["Price"].max()]
    low_point = daily[daily["Price"] == daily["Price"].min()]
    chart_tooltip = [
        alt.Tooltip("Day:T", title="Date"),
        alt.Tooltip("Price:Q", title="Avg Price", format=",.2f"),
        alt.Tooltip("Moving Average:Q", title="7D MA", format=",.2f"),
        alt.Tooltip("ListingsChart:Q", title="Listings", format=",.0f"),
        alt.Tooltip("BuyOrders:Q", title="Buy Orders", format=",.0f"),
    ]
    price_chart = (
        alt.Chart(daily)
        .mark_line(color="#f0a23b", interpolate="monotone", strokeWidth=3)
        .encode(
            x=alt.X(
                "Day:T",
                title="Date",
                axis=alt.Axis(labelColor="#9eabc0", titleColor="#c6cfdd"),
            ),
            y=alt.Y(
                "Price:Q",
                title="Price (CNY)",
                axis=alt.Axis(labelColor="#9eabc0", titleColor="#c6cfdd"),
                scale=alt.Scale(zero=False),
            ),
            tooltip=chart_tooltip,
        )
        .properties(height=320)
    )
    moving_average = (
        alt.Chart(daily)
        .mark_line(color="#49a078", interpolate="monotone", strokeDash=[6, 4], strokeWidth=2)
        .encode(
            x="Day:T",
            y=alt.Y("Moving Average:Q", axis=None, scale=alt.Scale(zero=False)),
            tooltip=chart_tooltip,
        )
    )
    extreme_points = alt.layer(
        alt.Chart(high_point)
        .mark_point(color="#ff6b6b", filled=True, size=90)
        .encode(
            x="Day:T",
            y=alt.Y("Price:Q", axis=None, scale=alt.Scale(zero=False)),
            tooltip=chart_tooltip,
        ),
        alt.Chart(low_point)
        .mark_point(color="#6dd6ff", filled=True, size=90)
        .encode(
            x="Day:T",
            y=alt.Y("Price:Q", axis=None, scale=alt.Scale(zero=False)),
            tooltip=chart_tooltip,
        ),
    )
    stock_overlay = (
        alt.Chart(daily)
        .mark_line(color="#5f7bd0", interpolate="monotone", strokeWidth=2.2, opacity=0.85)
        .encode(
            x=alt.X("Day:T", title="Date"),
            y=alt.Y(
                "ListingsChart:Q",
                title="Sell Stock",
                axis=alt.Axis(orient="right", labelColor="#aab6ca", titleColor="#aab6ca"),
            ),
            tooltip=chart_tooltip,
        )
        .properties(height=320)
    )
    return alt.layer(price_chart, moving_average, extreme_points, stock_overlay).resolve_scale(
        y="independent"
    )
