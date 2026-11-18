from __future__ import annotations

from pathlib import Path

from app.demo_data import load_demo
from app.models import Snapshot
from app.signals import build_signals, top_signals


def _snapshot(
    date: str,
    *,
    price: float | None = 100.0,
    rating: float | None = 4.6,
    reviews: int | None = 1000,
    sales_value: int | None = 1000,
    sales_text: str | None = "1K+ bought in past month",
    seller: str | None = "Amazon.com",
    in_stock: bool | None = True,
    data_gaps: list[str] | None = None,
) -> Snapshot:
    return Snapshot(
        product_id="B09C13PZX7",
        snapshot_date=date,
        title="Test Product",
        price=price,
        currency="$",
        rating=rating,
        reviews=reviews,
        sales_value=sales_value,
        sales_text=sales_text,
        bullets=["bullet"],
        description="description",
        main_image="https://m.media-amazon.com/images/I/x._AC_SL1500_.jpg",
        gallery_images=["https://m.media-amazon.com/images/I/y._AC_SL1500_.jpg"],
        in_stock=in_stock,
        seller=seller,
        data_gaps=data_gaps or [],
    )


def test_price_and_seller_signals() -> None:
    previous = _snapshot("2026-01-03")
    current = _snapshot(
        "2026-11-18",
        price=90.0,
        seller="Sold by Third Party",
        reviews=1200,
    )
    signals = build_signals(current, [previous, current], "Test Product")
    kinds = {signal.kind for signal in signals}
    assert "price_change" in kinds
    assert "seller_change" in kinds
    assert "review_growth" in kinds
    assert any(signal.severity == "high" for signal in signals)


def test_missing_price_and_sales_signals() -> None:
    previous = _snapshot("2026-01-03")
    current = _snapshot(
        "2026-11-18",
        price=None,
        sales_value=None,
        sales_text=None,
        data_gaps=["价格", "预计销量"],
    )
    signals = build_signals(current, [previous, current])
    kinds = {signal.kind for signal in signals}
    assert "price_gap" in kinds
    assert "sales_gap" in kinds


def test_top_signals_prefers_high_severity() -> None:
    previous = _snapshot("2026-01-03")
    current = _snapshot(
        "2026-11-18",
        price=80.0,
        seller="Sold by Third Party",
    )
    signals = build_signals(current, [previous, current], "Test Product")
    top = top_signals(signals, limit=2)
    assert len(top) == 2
    assert all(signal.severity == "high" for signal in top)


def test_demo_signals_include_samsung_seller_context() -> None:
    demo = load_demo(Path("data/demo/snapshots.json"))
    products = {product.product_id: product for product in demo.products}
    all_signals = []
    for snapshot in demo.current_snapshots():
        history = demo.history(snapshot.product_id, demo.captured_at)
        all_signals.extend(
            build_signals(snapshot, history, products[snapshot.product_id].name)
        )
    top = top_signals(all_signals, limit=3)
    assert top
    assert any("Samsung T7" in signal.text for signal in top)
