from __future__ import annotations

from app.llm import MockAnalysisClient, fallback_analysis, parse_analysis_json
from app.models import Snapshot


def _snapshot(day: str, price: float, reviews: int, sales: int, sales_text: str) -> Snapshot:
    return Snapshot(
        product_id="mouse-a",
        snapshot_date=day,
        title="游戏鼠标 A",
        price=price,
        currency="$",
        rating=4.5,
        reviews=reviews,
        sales_value=sales,
        sales_text=sales_text,
        description="test",
        data_gaps=[],
    )


def test_mock_analysis_trend() -> None:
    history = [
        _snapshot("2025-11-15", 40.0, 1000, 1000, "1K+"),
        _snapshot("2025-11-16", 38.0, 1100, 1000, "1K+"),
        _snapshot("2025-11-17", 36.0, 1200, 1000, "1K+"),
    ]
    analysis = MockAnalysisClient().analyze(
        {"name": "游戏鼠标 A"},
        history[-1],
        history,
    )
    assert analysis.confidence == "high"
    assert "下降" in analysis.price_trend
    assert "无法判断更细变化" in analysis.sales_trend
    assert any("价格变化" in item for item in analysis.key_changes)


def test_mock_analysis_gap_lowers_confidence() -> None:
    history = [_snapshot("2025-11-15", 40.0, 1000, 1000, "1K+")]
    history[0].data_gaps = ["预计销量"]
    analysis = MockAnalysisClient().analyze({"name": "游戏鼠标 A"}, history[0], history)
    assert analysis.confidence == "low"
    assert "预计销量" in analysis.data_gaps


def test_parse_analysis_json() -> None:
    current = _snapshot("2025-11-17", 36.0, 1200, 1000, "1K+")
    text = """
    {
      "title": "测试",
      "summary": "摘要",
      "price_trend": "价格下降",
      "sales_trend": "销量持平",
      "key_changes": ["价格变化"],
      "actions": ["观察"],
      "confidence": "medium",
      "data_gaps": []
    }
    """
    analysis = parse_analysis_json(text, current)
    assert analysis.product_id == "mouse-a"
    assert analysis.snapshot_date == "2025-11-17"
    assert analysis.confidence == "medium"


def test_parse_analysis_json_coerces_string_lists() -> None:
    current = _snapshot("2025-11-17", 36.0, 1200, 1000, "1K+")
    text = """
    {
      "title": "测试",
      "summary": "摘要",
      "price_trend": "价格下降",
      "sales_trend": "销量持平",
      "key_changes": "只有一个变化",
      "actions": "观察",
      "confidence": "medium"
    }
    """
    analysis = parse_analysis_json(text, current)
    assert analysis.key_changes == ["只有一个变化"]
    assert analysis.actions == ["观察"]
    assert analysis.data_gaps == current.data_gaps


def test_fallback_analysis() -> None:
    current = _snapshot("2025-11-17", 36.0, 1200, 1000, "1K+")
    analysis = fallback_analysis(current, "invalid json")
    assert analysis.confidence == "low"
    assert any("invalid json" in gap for gap in analysis.data_gaps)
