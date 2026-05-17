from __future__ import annotations

from main import normalize_history_values


def test_empty_input():
    df = normalize_history_values([])
    assert list(df.columns)
    assert df.empty


def test_missing_columns():
    rows = [
        [
            "Timestamp",
            "Goods ID",
            "Family",
            "Knife Type",
            "Skin Name",
            "Condition",
            "Price",
            "Listings",
        ],
        [
            "2026-05-17 00:00:00",
            "1",
            "Karambit",
            "Karambit",
            "Karambit | Doppler",
            "Factory New",
            "100",
            "10",
        ],
    ]
    df = normalize_history_values(rows)
    assert "Buy Orders" in df.columns
    assert "Image URL" in df.columns


def test_family_condition_derived_from_skin_name():
    rows = [
        [
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
        ],
        [
            "2026-05-17 00:00:00",
            "1",
            "",
            "",
            "Butterfly Knife | Doppler (Factory New)",
            "",
            "100",
            "10",
            "",
            "",
            "",
        ],
    ]
    df = normalize_history_values(rows)
    assert df.iloc[0]["Family"].startswith("Butterfly Knife")
    assert df.iloc[0]["Condition"] == "Factory New"


def test_duplicate_timestamps_deduplication():
    rows = [
        [
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
        ],
        [
            "2026-05-17 00:00:00",
            "1",
            "Karambit",
            "Karambit",
            "Karambit | Doppler",
            "Factory New",
            "100",
            "10",
            "1",
            "",
            "",
        ],
        [
            "2026-05-17 00:00:00",
            "1",
            "Karambit",
            "Karambit",
            "Karambit | Doppler",
            "Factory New",
            "101",
            "11",
            "1",
            "",
            "",
        ],
    ]
    df = normalize_history_values(rows)
    dedup = df.drop_duplicates(subset=["Timestamp", "Goods ID"], keep="last")
    assert len(dedup) == 1
