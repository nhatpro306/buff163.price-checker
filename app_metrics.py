from __future__ import annotations

import html

import pandas as pd


def money(value: object) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    return "N/A" if pd.isna(numeric) else f"{float(numeric):,.2f} CNY"


def whole(value: object) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    return "N/A" if pd.isna(numeric) else f"{int(numeric):,}"


def price_delta(frame: pd.DataFrame) -> tuple[float | None, float | None]:
    prices = pd.to_numeric(frame.get("Price"), errors="coerce").dropna()
    if len(prices) < 2:
        return None, None
    first = float(prices.iloc[0])
    last = float(prices.iloc[-1])
    if first == 0:
        return last - first, None
    return last - first, ((last - first) / first) * 100


def trend_direction(frame: pd.DataFrame) -> str:
    _, change_pct = price_delta(frame)
    if change_pct is None:
        return "Neutral"
    if change_pct > 0.25:
        return "Bullish"
    if change_pct < -0.25:
        return "Bearish"
    return "Sideways"


def market_volatility(frame: pd.DataFrame) -> str:
    prices = pd.to_numeric(frame.get("Price"), errors="coerce").dropna()
    if len(prices) < 3:
        return "N/A"
    returns = prices.pct_change().dropna()
    if returns.empty:
        return "N/A"
    return f"{float(returns.std() * 100):.2f}%"


def dashboard_kpis(frame: pd.DataFrame, sell_stock: int) -> str:
    prices = pd.to_numeric(frame.get("Price"), errors="coerce").dropna()
    latest_price = prices.iloc[-1] if not prices.empty else pd.NA
    _, change_pct = price_delta(frame)
    trend = trend_direction(frame)
    trend_class = "positive" if trend == "Bullish" else "negative" if trend == "Bearish" else ""
    change_class = (
        "positive"
        if change_pct is not None and change_pct >= 0
        else "negative" if change_pct is not None else ""
    )
    rows = [
        ("Latest Price", money(latest_price), change_class),
        ("Average Price", money(prices.mean() if not prices.empty else pd.NA), ""),
        ("Highest Price", money(prices.max() if not prices.empty else pd.NA), ""),
        ("Lowest Price", money(prices.min() if not prices.empty else pd.NA), ""),
        ("24h Change %", "N/A" if change_pct is None else f"{change_pct:+.2f}%", change_class),
        ("Total Listings", whole(sell_stock), ""),
        ("Trend Direction", trend, trend_class),
        ("Market Volatility", market_volatility(frame), ""),
    ]
    return "".join(
        '<div class="dash-kpi-card">'
        f"<span>{html.escape(label)}</span>"
        f'<strong class="{value_class}">{html.escape(value)}</strong>'
        "</div>"
        for label, value, value_class in rows
    )


def market_signal_cards(frame: pd.DataFrame, sell_stock: int, buy_orders: int) -> str:
    trend = trend_direction(frame)
    volatility = market_volatility(frame)
    liquidity = "Thin" if sell_stock <= 0 else "Active" if sell_stock >= 10 else "Limited"
    pressure = (
        "Buy-side pressure"
        if buy_orders > sell_stock and sell_stock > 0
        else "Sell-side supply" if sell_stock > buy_orders else "Balanced book"
    )
    rows = [
        ("Trend Analysis", trend),
        ("Volatility Detection", volatility),
        ("Liquidity Signal", liquidity),
        ("Smart Market Signal", pressure),
    ]
    return "".join(
        '<div class="signal-card">'
        f"<span>{html.escape(label)}</span>"
        f"<strong>{html.escape(value)}</strong>"
        "</div>"
        for label, value in rows
    )


def top_movers(frame: pd.DataFrame, limit: int = 6) -> pd.DataFrame:
    if frame.empty or not {"Family", "Timestamp", "Price"}.issubset(frame.columns):
        return pd.DataFrame(columns=["Family", "Latest Price", "Change %", "Listings"])
    scoped = frame.dropna(subset=["Family", "Timestamp", "Price"]).sort_values("Timestamp")
    rows = []
    for family, group in scoped.groupby("Family"):
        prices = pd.to_numeric(group["Price"], errors="coerce").dropna()
        if len(prices) < 2 or float(prices.iloc[0]) == 0:
            continue
        latest = group.iloc[-1]
        change_pct = (
            (float(prices.iloc[-1]) - float(prices.iloc[0])) / float(prices.iloc[0])
        ) * 100
        rows.append(
            {
                "Family": family,
                "Latest Price": float(prices.iloc[-1]),
                "Change %": change_pct,
                "Listings": latest.get("Listings", pd.NA),
            }
        )
    if not rows:
        return pd.DataFrame(columns=["Family", "Latest Price", "Change %", "Listings"])
    result = pd.DataFrame(rows)
    return result.reindex(result["Change %"].abs().sort_values(ascending=False).index).head(limit)
