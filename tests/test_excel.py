from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from app.excel_io import load_watchlist, read_history, write_snapshots
from app.models import Snapshot

EXCEL = Path(__file__).resolve().parents[1] / "data" / "source" / "amazon_products.xlsx"


def test_load_watchlist() -> None:
    products = load_watchlist(EXCEL)
    assert [product.product_id for product in products] == [
        "B09C13PZX7",
        "B0DZZWMB2L",
        "B0DZFVBQLK",
        "B0874XWW23",
    ]
    assert products[0].excel_sheet == "雷蛇鼠标"
    assert products[3].category == "存储"


def test_read_history_dedupes_by_date() -> None:
    snapshots = read_history(EXCEL)
    assert len(snapshots) == 7
    razer = [item for item in snapshots if item.product_id == "B09C13PZX7"]
    assert [item.snapshot_date for item in razer] == [
        "2026-01-03",
        "2026-01-01",
        "2025-12-27",
        "2025-12-24",
    ]
    assert razer[0].price == 34.99
    assert razer[0].rating == 4.6
    assert razer[0].reviews == 9222
    assert razer[0].sales_value == 10000

    samsung = next(item for item in snapshots if item.product_id == "B0874XWW23")
    assert len(samsung.gallery_images) == 7
    assert any("_AC_SR38,50_" in url for url in samsung.gallery_images)
    assert any("play-icon-overlay" in url for url in samsung.gallery_images)


def test_write_snapshots_appends_and_updates(tmp_path: Path) -> None:
    out_path = tmp_path / "collected.xlsx"
    snapshot = Snapshot(
        product_id="B09C13PZX7",
        snapshot_date="2026-11-18",
        title="Razer Basilisk V3 Customizable RGB Wired",
        price=32.99,
        list_price=49.99,
        currency="$",
        rating=4.6,
        reviews=10769,
        sales_value=5000,
        sales_text="5K+ bought in past month",
        bullets=["bullet one", "bullet two"],
        description="description",
        main_image="https://m.media-amazon.com/images/I/61AcT0ZuO3L._AC_SL1500_.jpg",
        gallery_images=[
            "https://m.media-amazon.com/images/I/31N1BZUZLwL._AC_SL1500_.jpg",
            "https://m.media-amazon.com/images/I/51XpciVLsRL._AC_SL1500_.jpg",
        ],
        in_stock=True,
        availability="In Stock",
        data_gaps=[],
    )

    first = write_snapshots(EXCEL, [snapshot], out_path=out_path)
    assert first.path == out_path
    assert first.appended == ["B09C13PZX7"]

    workbook = load_workbook(out_path)
    sheet = workbook["雷蛇鼠标"]
    assert sheet.max_row == 9
    assert sheet.cell(row=9, column=6).value == "$32.99"
    assert sheet.cell(row=9, column=7).value == "5K+ bought in past month"
    date_cell = sheet.cell(row=9, column=10).value
    assert isinstance(date_cell, datetime)
    assert date_cell.date().isoformat() == "2026-11-18"

    snapshot.price = 31.99
    second = write_snapshots(EXCEL, [snapshot], out_path=out_path)
    assert second.updated == ["B09C13PZX7"]
    workbook = load_workbook(out_path)
    sheet = workbook["雷蛇鼠标"]
    assert sheet.max_row == 9
    assert sheet.cell(row=9, column=6).value == "$31.99"
