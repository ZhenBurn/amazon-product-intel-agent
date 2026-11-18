from __future__ import annotations

from app.llm import MockAnalysisClient
from app.llm_guard import extract_numbers, validate_analysis
from app.models import ProductAnalysis, Snapshot


def _snapshot(
    date: str,
    *,
    price: float | None,
    rating: float | None,
    reviews: int | None,
    sales_value: int | None,
    sales_text: str | None,
    title: str = "Samsung T7 Portable SSD",
) -> Snapshot:
    return Snapshot(
        product_id="B0874XWW23",
        snapshot_date=date,
        title=title,
        price=price,
        list_price=None,
        currency="$",
        rating=rating,
        reviews=reviews,
        sales_value=sales_value,
        sales_text=sales_text,
        bullets=["bullet"],
        description="description",
        main_image="https://m.media-amazon.com/images/I/x._AC_SL1500_.jpg",
        gallery_images=["https://m.media-amazon.com/images/I/y._AC_SL1500_.jpg"],
        in_stock=True,
        availability="In Stock",
        data_gaps=[],
    )


def _analysis(summary: str, *, key_changes: list[str] | None = None) -> ProductAnalysis:
    return ProductAnalysis(
        product_id="B0874XWW23",
        snapshot_date="2026-11-18",
        title="测试",
        summary=summary,
        price_trend="未生成",
        sales_trend="未生成",
        key_changes=key_changes or [],
        actions=[],
        confidence="medium",
        data_gaps=[],
    )


def test_extract_numbers() -> None:
    tokens = extract_numbers(
        "价格 $1,388.97，销量 10K+，增长 132.5%，速度 1,050MB/s"
    )
    values = [(token.value, token.is_percent) for token in tokens]
    assert (1388.97, False) in values
    assert (10000.0, False) in values
    assert (132.5, True) in values
    assert (1050.0, False) in values


def test_mock_analysis_passes_grounding() -> None:
    history = [
        _snapshot(
            "2025-12-24",
            price=187.99,
            rating=4.7,
            reviews=37101,
            sales_value=5000,
            sales_text="5K+ bought in past month",
        ),
        _snapshot(
            "2026-01-03",
            price=187.99,
            rating=4.7,
            reviews=37101,
            sales_value=5000,
            sales_text="5K+ bought in past month",
        ),
        _snapshot(
            "2026-11-18",
            price=436.99,
            rating=4.7,
            reviews=5132,
            sales_value=1000,
            sales_text="1K+ bought in past month",
        ),
    ]
    analysis = MockAnalysisClient().analyze(
        {"name": "Samsung T7"}, history[-1], history
    )
    result = validate_analysis(analysis, history[-1], history, {"name": "Samsung T7"})
    assert result.ok, result.violations


def test_guard_rejects_fabricated_percentage() -> None:
    current = _snapshot(
        "2026-11-18",
        price=436.99,
        rating=4.7,
        reviews=5132,
        sales_value=1000,
        sales_text="1K+ bought in past month",
    )
    history = [
        _snapshot(
            "2026-01-03",
            price=187.99,
            rating=4.7,
            reviews=37101,
            sales_value=5000,
            sales_text="5K+ bought in past month",
        ),
        current,
    ]
    result = validate_analysis(
        _analysis("价格下降了 50%"),
        current,
        history,
    )
    assert not result.ok
    assert any("50%" in item for item in result.violations)


def test_guard_rejects_fabricated_reviews() -> None:
    current = _snapshot(
        "2026-11-18",
        price=436.99,
        rating=4.7,
        reviews=5132,
        sales_value=1000,
        sales_text="1K+ bought in past month",
    )
    result = validate_analysis(
        _analysis("评价数达到 99999"),
        current,
        [current],
    )
    assert not result.ok
    assert any("99999" in item for item in result.violations)


def test_guard_accepts_rounded_percentage() -> None:
    current = _snapshot(
        "2026-11-18",
        price=436.99,
        rating=4.7,
        reviews=5132,
        sales_value=1000,
        sales_text="1K+ bought in past month",
    )
    history = [
        _snapshot(
            "2026-01-03",
            price=187.99,
            rating=4.7,
            reviews=37101,
            sales_value=5000,
            sales_text="5K+ bought in past month",
        ),
        current,
    ]
    result = validate_analysis(
        _analysis("价格上升 132.5%"),
        current,
        history,
    )
    assert result.ok, result.violations


def test_guard_allows_older_history_price() -> None:
    current = _snapshot(
        "2026-11-18",
        price=None,
        rating=4.6,
        reviews=10769,
        sales_value=5000,
        sales_text="5K+ bought in past month",
    )
    history = [
        _snapshot(
            "2025-12-24",
            price=31.99,
            rating=4.6,
            reviews=9215,
            sales_value=10000,
            sales_text="10K+ bought in past month",
        ),
        _snapshot(
            "2026-01-03",
            price=34.99,
            rating=4.6,
            reviews=9222,
            sales_value=10000,
            sales_text="10K+ bought in past month",
        ),
        current,
    ]
    result = validate_analysis(
        _analysis("上一次价格为 $31.99，当前价格缺失。"),
        current,
        history,
    )
    assert result.ok, result.violations


def test_guard_accepts_numbers_from_product_title() -> None:
    current = _snapshot(
        "2026-11-18",
        price=None,
        rating=4.4,
        reviews=649,
        sales_value=None,
        sales_text=None,
        title="ASUS ROG Strix G16 (2025) Gaming Laptop, RTX 5070",
    )
    result = validate_analysis(
        _analysis("ASUS ROG Strix G16 (2025) 的 RTX 5070 版本，价格缺失。"),
        current,
        [current],
    )
    assert result.ok, result.violations
