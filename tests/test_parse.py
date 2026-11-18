from __future__ import annotations

import pytest

from app.errors import BlockedError
from app.images import image_key
from app.parse import detect_page_state, parse_product_page
from tests.amazon_fixture import captcha_page, render_page


def test_parse_normal_page() -> None:
    parsed = parse_product_page(render_page())
    assert parsed.title.startswith("Razer Basilisk")
    assert parsed.price_text == "$34.99"
    assert parsed.list_price_text == "$49.99"
    assert parsed.rating_text == "4.6 out of 5 stars"
    assert parsed.reviews_text == "(9,215 ratings)"
    assert parsed.sales_text == "10K+ bought in past month"
    assert len(parsed.bullets) == 3
    assert parsed.description is not None
    assert parsed.main_image is not None
    assert parsed.availability == "In Stock"
    assert parsed.selector_hits["price"].startswith("#corePriceDisplay")
    assert parsed.selector_hits["bullets"].startswith("#feature-bullets")


def test_parse_gallery_upgrades_and_dedupes() -> None:
    parsed = parse_product_page(render_page())
    assert len(parsed.gallery_images) == 3
    assert all("_AC_SL1500_" in url for url in parsed.gallery_images[:2])
    assert "play-icon-overlay" in parsed.gallery_images[-1]
    assert image_key(parsed.main_image) not in {image_key(url) for url in parsed.gallery_images}


def test_parse_json_ld_price_fallback() -> None:
    parsed = parse_product_page(render_page(price="$1,388.97", json_ld_price=True))
    assert parsed.price_text == "$1388.97"
    assert parsed.selector_hits["price"] == "json-ld.offers.price"


def test_parse_missing_sales() -> None:
    parsed = parse_product_page(render_page(sales=None))
    assert parsed.sales_text is None


def test_parse_captcha_raises() -> None:
    with pytest.raises(BlockedError):
        parse_product_page(captcha_page())


def test_detect_page_state() -> None:
    assert detect_page_state(captcha_page()) == "captcha"
    assert detect_page_state("<html><body>Sorry! Something went wrong</body></html>") == "blocked"
    assert detect_page_state(render_page()) == "ok"
