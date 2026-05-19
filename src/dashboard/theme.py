from __future__ import annotations

import streamlit as st


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');
        :root {
            --bg-top: #090f17;
            --bg-main: #0d141f;
            --line: #263548;
            --accent: #4f8cff;
            --accent-2: #f7a83d;
            --green: #34d399;
            --red: #fb7185;
            --text: #f5f7fb;
            --muted: #9aa8bb;
            --soft: #d9dfeb;
            --panel: rgba(15, 23, 35, 0.92);
        }
        .stApp {
            background:
                radial-gradient(circle at 12% 0%, rgba(79, 140, 255, 0.14), transparent 30rem),
                radial-gradient(circle at 84% 8%, rgba(247, 168, 61, 0.09), transparent 24rem),
                linear-gradient(180deg, #070b12 0%, #0a1019 42%, #0b111b 100%);
            color: var(--text);
        }
        .stApp, .stApp p, .stApp span, .stApp div, .stApp label, .stApp li {
            color: var(--text);
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        .stMarkdown, .stMarkdown p, .stMarkdown span {
            color: var(--text) !important;
        }
        .block-container {
            max-width: 1440px;
            padding: 1rem 1.5rem 2rem;
        }
        .buff-nav {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            padding: 1rem 1.15rem;
            background: linear-gradient(135deg, rgba(11, 17, 28, 0.92), rgba(25, 34, 49, 0.86));
            border: 1px solid rgba(126, 146, 184, 0.28);
            border-radius: 8px;
            margin-bottom: 1.1rem;
            box-shadow: 0 18px 45px rgba(0, 0, 0, 0.26);
            backdrop-filter: blur(10px);
        }
        .buff-brand {
            display: flex;
            align-items: center;
            gap: 0.8rem;
            font-weight: 800;
            font-size: 1.05rem;
        }
        .buff-badge {
            width: 42px;
            height: 42px;
            border-radius: 8px;
            background: linear-gradient(135deg, #f0a23b 0%, #5076c8 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: 900;
            box-shadow: 0 10px 24px rgba(240, 162, 59, 0.22);
        }
        .buff-nav-subtitle {
            color: #aab6ca !important;
            font-size: 0.92rem;
        }
        .buff-picker-title {
            color: var(--muted) !important;
            font-size: 0.86rem;
            font-weight: 700;
            margin: 0.8rem 0 0.55rem;
            text-transform: uppercase;
        }
        .buff-knife-tile {
            height: 104px;
            border: 1px solid rgba(129, 149, 184, 0.28);
            border-radius: 8px;
            background:
                radial-gradient(circle at center, rgba(240, 162, 59, 0.13), transparent 50%),
                linear-gradient(180deg, rgba(32, 43, 61, 0.95), rgba(14, 20, 31, 0.98));
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 0.5rem;
            margin-bottom: 0.35rem;
            overflow: hidden;
        }
        .buff-knife-tile img {
            width: 100%;
            height: 84px;
            object-fit: contain;
            filter: drop-shadow(0 16px 16px rgba(0, 0, 0, 0.46));
        }
        .buff-knife-tile-active {
            border-color: rgba(240, 162, 59, 0.9);
            background:
                radial-gradient(circle at center, rgba(240, 162, 59, 0.24), transparent 52%),
                linear-gradient(180deg, rgba(47, 59, 79, 0.98), rgba(18, 25, 37, 0.99));
            box-shadow: inset 0 0 0 1px rgba(240, 162, 59, 0.18), 0 12px 26px rgba(0, 0, 0, 0.22);
        }
        .buff-selected-label {
            color: #f6b35d !important;
            font-size: 0.78rem;
            font-weight: 800;
            min-height: 1rem;
            margin-bottom: 0.15rem;
            text-align: center;
        }
        .buff-knife-empty {
            width: 100%;
            height: 72px;
            background: rgba(120, 138, 173, 0.08);
            border-radius: 6px;
        }
        div[data-testid="stButton"] > button {
            background: rgba(245, 247, 251, 0.075) !important;
            border: 1px solid rgba(170, 182, 202, 0.28) !important;
            color: #f5f7fb !important;
            border-radius: 8px !important;
            min-height: 2.6rem;
            font-weight: 700 !important;
            transition: border-color 120ms ease, background 120ms ease, transform 120ms ease;
        }
        div[data-testid="stButton"] > button p,
        div[data-testid="stButton"] > button span {
            color: #f5f7fb !important;
        }
        div[data-testid="stButton"] > button:hover {
            background: rgba(240, 162, 59, 0.2) !important;
            border-color: rgba(240, 162, 59, 0.78) !important;
            color: #ffffff !important;
            transform: translateY(-1px);
        }
        div[data-testid="stButton"] > button:focus {
            box-shadow: 0 0 0 2px rgba(228, 144, 55, 0.35) !important;
        }
        .buff-hero {
            background:
                linear-gradient(135deg, rgba(17, 25, 37, 0.98) 0%, rgba(10, 15, 23, 0.98) 100%);
            border: 1px solid rgba(116, 135, 166, 0.24);
            border-radius: 10px;
            padding: 0;
            margin-bottom: 1rem;
            box-shadow: 0 22px 55px rgba(0, 0, 0, 0.34);
            overflow: hidden;
        }
        .buff-breadcrumb {
            color: var(--muted) !important;
            margin-bottom: 0.7rem;
            font-size: 0.9rem;
        }
        .buff-grid {
            display: grid;
            grid-template-columns: minmax(300px, 42%) minmax(0, 58%);
            gap: 0;
            align-items: stretch;
        }
        .buff-image-card {
            grid-row: 1 / span 2;
            background:
                radial-gradient(circle at center, rgba(79, 140, 255, 0.2), transparent 58%),
                linear-gradient(180deg, #1b2635 0%, #101823 100%);
            border-radius: 0;
            min-height: 380px;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 0;
            border-right: 1px solid #24303c;
            overflow: hidden;
            padding: 1rem;
        }
        .buff-knife-art {
            width: 100%;
            height: 250px;
            object-fit: contain;
            object-position: center;
            filter: drop-shadow(0 18px 24px rgba(0, 0, 0, 0.35));
        }
        .buff-title {
            font-size: clamp(1.65rem, 2.55vw, 2.35rem);
            font-weight: 800;
            margin: 0 0 0.65rem;
            color: var(--text) !important;
            line-height: 1.1;
        }
        .buff-item-main {
            grid-column: 2;
            grid-row: 1;
            padding: 1.2rem 1.25rem;
            display: flex;
            flex-direction: column;
            justify-content: flex-start;
        }
        .buff-market-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-bottom: 0.7rem;
        }
        .buff-market-tags span {
            background: #1b2631;
            border: 1px solid #303c49;
            border-radius: 3px;
            color: #c7d0dc !important;
            font-size: 0.78rem;
            font-weight: 700;
            padding: 0.28rem 0.5rem;
        }
        .buff-submeta {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.45rem;
            margin: 0;
        }
        .buff-submeta span {
            display: flex;
            justify-content: space-between;
            gap: 0.75rem;
            background: #151f29;
            border: 1px solid #2a3644;
            border-radius: 4px;
            color: #d9dfeb !important;
            font-size: 0.86rem;
            padding: 0.45rem 0.55rem;
        }
        .buff-submeta strong {
            color: #ffffff !important;
            text-align: right;
        }
        .buff-price-panel {
            grid-column: 2;
            grid-row: 2;
            background:
                radial-gradient(circle at top right, rgba(247, 168, 61, 0.13), transparent 15rem),
                #090f16;
            border-left: 1px solid rgba(116, 135, 166, 0.22);
            border-top: 1px solid rgba(116, 135, 166, 0.22);
            padding: 1.35rem 1.25rem;
        }
        .buff-price-label {
            color: #8793a1 !important;
            font-size: 0.78rem;
            font-weight: 700;
            text-transform: uppercase;
        }
        .buff-price-value {
            color: #ffb23f !important;
            font-size: clamp(1.8rem, 3vw, 2.45rem);
            font-weight: 900;
            line-height: 1.15;
            margin: 0.2rem 0 0.85rem;
        }
        .buff-price-row {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            border-top: 1px solid #24303c;
            color: #c7d0dc !important;
            font-size: 0.82rem;
            padding: 0.45rem 0;
        }
        .buff-price-row strong {
            color: #f5f7fb !important;
            font-weight: 800;
        }
        .buff-price-micro {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.55rem;
            margin: 0.9rem 0 0.8rem;
        }
        .buff-price-micro span {
            background: rgba(17, 26, 39, 0.88);
            border: 1px solid rgba(116, 135, 166, 0.2);
            border-radius: 8px;
            padding: 0.65rem;
            color: #8f9baa !important;
            font-size: 0.72rem;
            font-weight: 800;
            text-transform: uppercase;
        }
        .buff-price-micro strong {
            display: block;
            color: #f5f7fb !important;
            font-size: 0.95rem;
            line-height: 1.15;
            margin-top: 0.3rem;
            text-transform: none;
            overflow-wrap: anywhere;
        }
        .buff-price-stats {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            column-gap: 0.85rem;
            margin-top: 0.15rem;
        }
        .buff-market-tabs {
            display: flex;
            gap: 0.35rem;
            margin-top: 1rem;
        }
        .buff-market-tabs span {
            background: #19232e;
            border: 1px solid #303c49;
            border-radius: 3px;
            color: #c7d0dc !important;
            font-size: 0.82rem;
            font-weight: 800;
            padding: 0.45rem 0.7rem;
        }
        .buff-market-tabs span:first-child {
            background: #ffb23f;
            border-color: #ffb23f;
            color: #111820 !important;
        }
        .buff-statline {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.75rem;
            margin-top: 1.1rem;
        }
        .buff-ref {
            color: var(--soft) !important;
            background: rgba(8, 13, 22, 0.32);
            border: 1px solid rgba(126, 146, 184, 0.22);
            border-radius: 8px;
            padding: 0.78rem 0.85rem;
        }
        .buff-ref strong {
            color: #ffb23f !important;
            display: block;
            font-size: 1.45rem;
            margin: 0.15rem 0 0;
            line-height: 1.15;
        }
        .buff-panel {
            background: linear-gradient(180deg, rgba(21, 27, 37, 0.94) 0%, rgba(18, 25, 35, 0.94) 100%);
            border: 1px solid rgba(95, 111, 142, 0.35);
            border-radius: 8px;
            padding: 1rem 1rem 0.6rem 1rem;
            box-shadow: 0 18px 40px rgba(0, 0, 0, 0.2);
        }
        .buff-panel-title {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin-bottom: 0.85rem;
        }
        .buff-panel-title h3 {
            margin: 0;
            color: var(--text) !important;
            font-size: 1.03rem;
        }
        .buff-chip {
            color: #dce4f6 !important;
            background: rgba(79, 111, 182, 0.24);
            border: 1px solid rgba(91, 122, 191, 0.45);
            border-radius: 999px;
            padding: 0.28rem 0.7rem;
            font-size: 0.82rem;
        }
        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div {
            background: rgba(19, 25, 35, 0.92) !important;
            border: 1px solid rgba(95, 111, 142, 0.35) !important;
            border-radius: 8px !important;
        }
        input, textarea {
            color: var(--text) !important;
            -webkit-text-fill-color: var(--text) !important;
        }
        div[data-baseweb="select"] * {
            color: var(--text) !important;
        }
        div[role="radiogroup"] {
            gap: 0.6rem;
        }
        div[role="radiogroup"] label {
            background: #111820;
            border: 1px solid #303c49;
            padding: 0.55rem 0.85rem;
            border-radius: 4px;
        }
        div[role="radiogroup"] label p {
            color: var(--soft) !important;
            font-weight: 600;
        }
        button[data-baseweb="tab"] {
            color: var(--muted) !important;
            background: rgba(19, 25, 35, 0.55) !important;
            border-radius: 12px 12px 0 0 !important;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            color: var(--text) !important;
            background: rgba(79, 111, 182, 0.18) !important;
        }
        div[data-testid="stDataFrame"] {
            border-radius: 16px;
            overflow: hidden;
            border: 1px solid rgba(95, 111, 142, 0.28);
        }
        .stApp {
            background: #0b111b;
        }
        .block-container {
            padding-top: 1rem;
        }
        section[data-testid="stSidebar"] {
            background: #0e1623;
            border-right: 1px solid rgba(132, 150, 178, 0.18);
        }
        @media (min-width: 900px) {
            section[data-testid="stSidebar"] {
                min-width: 19rem !important;
                transform: none !important;
                width: 19rem !important;
            }
            button[data-testid="stExpandSidebarButton"] {
                display: none !important;
            }
        }
        section[data-testid="stSidebar"] > div {
            padding-top: 1.1rem;
        }
        section[data-testid="stSidebar"] h1,
        section[data-testid="stSidebar"] h2,
        section[data-testid="stSidebar"] h3,
        section[data-testid="stSidebar"] label p {
            color: #e9eef8 !important;
        }
        .buff-sidebar-head {
            border: 1px solid rgba(132, 150, 178, 0.22);
            background: rgba(18, 27, 40, 0.96);
            border-radius: 12px;
            padding: 0.9rem;
            margin-bottom: 1rem;
        }
        .buff-sidebar-head strong {
            display: block;
            color: #f5f7fb !important;
            font-size: 1rem;
        }
        .buff-sidebar-head span {
            color: #9eabc0 !important;
            font-size: 0.82rem;
        }
        .buff-header {
            display: flex;
            justify-content: space-between;
            gap: 1rem;
            align-items: flex-start;
            background: rgba(10, 16, 25, 0.7);
            border: 1px solid rgba(116, 135, 166, 0.2);
            border-radius: 10px;
            padding: 1rem 1.15rem;
            margin-bottom: 1rem;
            box-shadow: 0 18px 40px rgba(0, 0, 0, 0.2);
            backdrop-filter: blur(10px);
        }
        .buff-header h1 {
            margin: 0;
            color: #f5f7fb !important;
            font-size: clamp(1.45rem, 2.5vw, 2.2rem);
            letter-spacing: 0;
        }
        .buff-header p {
            color: #9eabc0 !important;
            margin: 0.35rem 0 0;
        }
        .buff-status {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            border: 1px solid rgba(73, 160, 120, 0.45);
            background: rgba(73, 160, 120, 0.12);
            color: #9be7c4 !important;
            border-radius: 999px;
            padding: 0.42rem 0.7rem;
            white-space: nowrap;
            font-size: 0.82rem;
            font-weight: 700;
        }
        .buff-status-warn {
            border-color: rgba(240, 162, 59, 0.48);
            background: rgba(240, 162, 59, 0.13);
            color: #ffd08a !important;
        }
        .buff-section-title {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin: 0.9rem 0 0.55rem;
        }
        .buff-section-title h3 {
            margin: 0;
            font-size: 1.05rem;
            color: #f5f7fb !important;
        }
        .buff-section-title span {
            color: #9eabc0 !important;
            font-size: 0.86rem;
        }
        .buff-empty {
            border: 1px solid rgba(240, 162, 59, 0.35);
            background: rgba(240, 162, 59, 0.08);
            border-radius: 12px;
            padding: 1rem;
            margin: 0.75rem 0;
        }
        .buff-empty strong {
            display: block;
            color: #ffe0ad !important;
            margin-bottom: 0.25rem;
        }
        .buff-empty span {
            color: #c6cfdd !important;
        }
        div[data-testid="stMetric"] {
            border-radius: 14px;
            background: #111a28;
            border: 1px solid rgba(132, 150, 178, 0.2);
            box-shadow: 0 12px 28px rgba(0, 0, 0, 0.18);
            transition: transform 120ms ease, border-color 120ms ease;
        }
        div[data-testid="stMetric"]:hover {
            transform: translateY(-1px);
            border-color: rgba(240, 162, 59, 0.42);
        }
        div[data-testid="stMetricValue"] {
            font-size: clamp(1.35rem, 1.8vw, 1.85rem) !important;
            line-height: 1.12 !important;
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: clip !important;
        }
        button[data-baseweb="tab"] {
            border-radius: 10px !important;
            margin-right: 0.35rem !important;
        }
        div[data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 0.25rem;
            border-bottom: 1px solid rgba(132, 150, 178, 0.18);
        }
        div[data-testid="stDataFrame"] {
            border-radius: 12px;
            background: #111a28;
            border-color: rgba(132, 150, 178, 0.2);
        }
        div[data-testid="stSpinner"] {
            color: #f5f7fb !important;
        }
        .dash-tagline {
            color: #9eabc0 !important;
            font-size: 0.95rem;
            margin-top: 0.45rem !important;
            max-width: 760px;
        }
        .dash-kpi-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.85rem;
            margin: 1rem 0 1.15rem;
        }
        .dash-kpi-card,
        .signal-card {
            background:
                linear-gradient(180deg, rgba(17, 27, 39, 0.96) 0%, rgba(10, 17, 27, 0.96) 100%);
            border: 1px solid rgba(116, 135, 166, 0.22);
            border-radius: 10px;
            box-shadow: 0 14px 30px rgba(0, 0, 0, 0.22);
            padding: 0.9rem;
            transition: transform 120ms ease, border-color 120ms ease, background 120ms ease;
        }
        .dash-kpi-card:hover,
        .signal-card:hover {
            transform: translateY(-1px);
            border-color: rgba(247, 168, 61, 0.45);
            background:
                linear-gradient(180deg, rgba(21, 33, 48, 0.98) 0%, rgba(12, 20, 31, 0.98) 100%);
        }
        .dash-kpi-card span,
        .signal-card span {
            color: #8f9baa !important;
            display: block;
            font-size: 0.78rem;
            font-weight: 800;
            letter-spacing: 0.02em;
            text-transform: uppercase;
        }
        .dash-kpi-card strong {
            color: #f6f8fb !important;
            display: block;
            font-size: clamp(1.05rem, 1.55vw, 1.42rem);
            line-height: 1.15;
            margin-top: 0.45rem;
            overflow-wrap: anywhere;
        }
        .positive {
            color: var(--green) !important;
        }
        .negative {
            color: var(--red) !important;
        }
        .dashboard-grid {
            display: grid;
            grid-template-columns: minmax(0, 2.1fr) minmax(300px, 1fr);
            gap: 1rem;
            align-items: start;
        }
        .dashboard-panel {
            background: rgba(14, 22, 32, 0.94);
            border: 1px solid rgba(116, 135, 166, 0.22);
            border-radius: 10px;
            padding: 1rem;
            box-shadow: 0 16px 34px rgba(0, 0, 0, 0.22);
        }
        .chart-shell {
            background: rgba(14, 22, 32, 0.94);
            border: 1px solid rgba(116, 135, 166, 0.22);
            border-radius: 10px;
            padding: 0.75rem;
            box-shadow: 0 16px 34px rgba(0, 0, 0, 0.22);
        }
        .chart-legend {
            display: flex;
            flex-wrap: wrap;
            gap: 0.65rem 1rem;
            margin: 0 0 0.75rem;
        }
        .chart-legend span {
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
            color: #aeb9ca !important;
            font-size: 0.82rem;
            font-weight: 700;
        }
        .chart-legend i {
            width: 1.6rem;
            height: 0.22rem;
            border-radius: 999px;
            display: inline-block;
        }
        .legend-price { background: #f0a23b; }
        .legend-ma { background: #49a078; border-top: 2px dashed #49a078; height: 0 !important; }
        .legend-stock { background: #5f7bd0; }
        .legend-high { background: #ff6b6b; }
        .legend-low { background: #6dd6ff; }
        .signal-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.75rem;
        }
        .signal-card strong {
            color: #f6f8fb !important;
            display: block;
            font-size: 1rem;
            margin-top: 0.45rem;
        }
        .raw-section {
            margin-top: 1rem;
        }
        @media (max-width: 1100px) {
            .buff-grid {
                grid-template-columns: 1fr;
            }
            .buff-image-card,
            .buff-item-main,
            .buff-price-panel {
                grid-column: auto;
                grid-row: auto;
            }
            .dashboard-grid,
            .dash-kpi-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .buff-price-panel {
                border-left: 0;
                border-top: 1px solid #24303c;
            }
            .buff-statline {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .buff-image-card {
                min-height: 240px;
            }
            .buff-knife-art {
                height: 220px;
            }
            .buff-nav {
                align-items: flex-start;
                flex-direction: column;
            }
            .buff-header {
                flex-direction: column;
            }
        }
        @media (max-width: 720px) {
            .dashboard-grid,
            .dash-kpi-grid,
            .signal-grid {
                grid-template-columns: 1fr;
            }
            .buff-submeta {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

