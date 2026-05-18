from __future__ import annotations

from src.page_parser import parse_goods_page_metadata


def test_parse_goods_page_metadata_extracts_info_image_and_variants():
    page = """
    <html>
      <head><meta property="og:image" content="//example/image.jpg"></head>
      <script>
        var goods_info = {"name": "Karambit | Doppler"} market_show.pre_init
      </script>
      <a class="x i_Btn y" data-goodsid="2">Factory New</a>
      <a class="x i_Btn y" data-goodsid="3">Minimal Wear</a>
      <div class="market-header black"></div>
      <a class="x i_Btn y" data-goodsid="999">Ignored</a>
    </html>
    """

    metadata = parse_goods_page_metadata(page, "1")

    assert metadata["name"] == "Karambit | Doppler"
    assert metadata["image_url"] == "//example/image.jpg"
    assert metadata["variant_goods_ids"] == ["1", "2", "3"]


def test_parse_goods_page_metadata_returns_seed_id_without_matches():
    assert parse_goods_page_metadata("<html></html>", "42") == {"variant_goods_ids": ["42"]}
