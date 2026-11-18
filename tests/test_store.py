from __future__ import annotations

from pathlib import Path

from app import store
from app.models import Product, Snapshot


def _product() -> Product:
    return Product(
        product_id="B09C13PZX7",
        name="Razer Basilisk V3",
        category="外设",
        url="https://www.amazon.com/dp/B09C13PZX7",
        excel_sheet="雷蛇鼠标",
    )


def _snapshot(price: float = 10.0) -> Snapshot:
    return Snapshot(
        product_id="B09C13PZX7",
        snapshot_date="2026-11-18",
        title="Razer Basilisk V3",
        price=price,
        list_price=49.99,
        currency="$",
        rating=4.6,
        reviews=100,
        sales_value=1000,
        sales_text="1K+ bought in past month",
        bullets=["bullet"],
        description="test",
        main_image="https://m.media-amazon.com/images/I/61AcT0ZuO3L._AC_SL1500_.jpg",
        gallery_images=["https://m.media-amazon.com/images/I/31N1BZUZLwL._AC_SL1500_.jpg"],
        in_stock=True,
        availability="In Stock",
        data_gaps=[],
        raw_html_path="data/raw/x.html.gz",
        selector_hits={"title": "#productTitle"},
    )


def test_upsert_snapshot_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = store.connect(db_path)
    store.init_db(conn)
    store.upsert_product(conn, _product())
    store.upsert_snapshot(conn, _snapshot(10.0))
    conn.commit()
    assert store.count_snapshots(conn) == 1

    store.upsert_snapshot(conn, _snapshot(9.0))
    conn.commit()
    assert store.count_snapshots(conn) == 1
    history = store.get_history(conn, "B09C13PZX7", "2026-11-18")
    assert history[0].price == 9.0
    assert history[0].bullets == ["bullet"]
    assert history[0].gallery_images
    assert history[0].selector_hits["title"] == "#productTitle"
    assert store.find_duplicate_snapshots(conn) == []
    conn.close()


def test_history_is_ordered(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = store.connect(db_path)
    store.init_db(conn)
    for day in ("2026-11-16", "2026-11-17", "2026-11-18"):
        snapshot = _snapshot(float(day[-2:]))
        snapshot.snapshot_date = day
        store.upsert_snapshot(conn, snapshot)
    conn.commit()

    history = store.get_history(conn, "B09C13PZX7", "2026-11-18", limit=5)
    assert [snapshot.snapshot_date for snapshot in history] == [
        "2026-11-16",
        "2026-11-17",
        "2026-11-18",
    ]
    conn.close()


def test_products_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    conn = store.connect(db_path)
    store.init_db(conn)
    store.upsert_product(conn, _product())
    conn.commit()
    products = store.list_products(conn)
    assert len(products) == 1
    assert products[0].url.endswith("B09C13PZX7")
    assert products[0].excel_sheet == "雷蛇鼠标"
    conn.close()
