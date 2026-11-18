from __future__ import annotations

from app.models import ParsedProduct
from app.normalize import build_snapshot, parse_price, parse_rating, parse_reviews, parse_sales
from tests.amazon_fixture import PRODUCT_A


def test_parse_price_formats() -> None:
    assert parse_price("$1,299.00") == (1299.0, "$")
    assert parse_price("US$39.99") == (39.99, "$")
    assert parse_price("USD 34.99") == (34.99, "$")
    assert parse_price("¥199.00") == (199.0, "¥")
    assert parse_price("价格暂缺") == (None, None)


def test_parse_rating_formats() -> None:
    assert parse_rating("4.6 out of 5 stars") == 4.6
    assert parse_rating("4.4 颗星，最多 5 颗星") == 4.4
    assert parse_rating("暂无评分") is None


def test_parse_reviews_formats() -> None:
    assert parse_reviews("(10,738 ratings)") == 10738
    assert parse_reviews("10,738 ratings") == 10738
    assert parse_reviews("(37,101)") == 37101
    assert parse_reviews("暂无评价") is None


def test_parse_sales_formats() -> None:
    assert parse_sales("10K+ bought in past month") == (10000, "10K+")
    assert parse_sales("500+ bought in past month") == (500, "500+")
    assert parse_sales("5K+ bought in past month") == (5000, "5K+")
    assert parse_sales("1.2K+ bought in past month") == (1200, "1.2K+")
    assert parse_sales("过去一个月 2K+ 人购买") == (2000, "2K+")
    assert parse_sales("950+ bought") == (950, "950+")


def test_build_snapshot_missing_price() -> None:
    parsed = ParsedProduct(
        title="Razer Basilisk V3",
        price_text=None,
        rating_text="4.6 out of 5 stars",
        reviews_text="(9,215 ratings)",
        sales_text="10K+ bought in past month",
        bullets=["bullet"],
        description="description",
        main_image="https://m.media-amazon.com/images/I/61AcT0ZuO3L._AC_SL1500_.jpg",
        gallery_images=["https://m.media-amazon.com/images/I/31N1BZUZLwL._AC_SL1500_.jpg"],
        availability="In Stock",
    )
    snapshot = build_snapshot(PRODUCT_A, "2026-11-18", parsed)
    assert snapshot.price is None
    assert "价格" in snapshot.data_gaps
    assert snapshot.rating == 4.6
    assert snapshot.reviews == 9215
    assert snapshot.sales_value == 10000
    assert snapshot.sales_text == "10K+ bought in past month"
    assert snapshot.in_stock is True


def test_build_snapshot_missing_sales_and_images() -> None:
    parsed = ParsedProduct(
        title="Razer Basilisk V3",
        price_text="$34.99",
        rating_text="4.6 out of 5 stars",
        reviews_text="(9,215 ratings)",
        sales_text=None,
    )
    snapshot = build_snapshot(PRODUCT_A, "2026-11-18", parsed)
    assert snapshot.price == 34.99
    assert snapshot.sales_value is None
    assert "预计销量" in snapshot.data_gaps
    assert "产品简介" in snapshot.data_gaps
    assert "主图" in snapshot.data_gaps
