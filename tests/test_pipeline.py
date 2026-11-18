from __future__ import annotations

import gzip
from pathlib import Path

from openpyxl import load_workbook

from app import store
from app.config import Settings
from app.pipeline import run_pipeline
from app.sources.amazon import AmazonSource
from tests.amazon_fixture import PRODUCT_A, PRODUCT_B, PRODUCT_C, captcha_page, render_page

EXCEL = Path(__file__).resolve().parents[1] / "data" / "source" / "amazon_products.xlsx"


def _cache(cache_dir: Path, asin: str, snapshot_date: str, html: str) -> None:
    path = cache_dir / asin / f"{snapshot_date}.html.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(html)


def test_pipeline_replay_and_idempotent(tmp_path: Path) -> None:
    cache_dir = tmp_path / "raw"
    _cache(cache_dir, PRODUCT_A.product_id, "2026-11-17", render_page(price="$34.99"))
    _cache(cache_dir, PRODUCT_A.product_id, "2026-11-18", render_page(price="$32.99"))
    _cache(cache_dir, PRODUCT_B.product_id, "2026-11-17", render_page(
        title="Samsung T7 Portable SSD",
        price="$187.99",
        rating="4.7 out of 5 stars",
        reviews="(37,101 ratings)",
        sales="5K+ bought in past month",
    ))
    _cache(cache_dir, PRODUCT_B.product_id, "2026-11-18", render_page(
        title="Samsung T7 Portable SSD",
        price="$186.99",
        rating="4.7 out of 5 stars",
        reviews="(37,150 ratings)",
        sales="5K+ bought in past month",
    ))

    settings = Settings(llm_mode="mock")
    source = AmazonSource(cache_dir=cache_dir, mode="replay")
    db_path = tmp_path / "test.db"
    report_dir = tmp_path / "reports"

    day1 = run_pipeline(
        settings,
        "2026-11-17",
        products=[PRODUCT_A, PRODUCT_B],
        source=source,
        db_path=db_path,
        report_dir=report_dir,
    )
    day2 = run_pipeline(
        settings,
        "2026-11-18",
        products=[PRODUCT_A, PRODUCT_B],
        source=source,
        db_path=db_path,
        report_dir=report_dir,
    )
    rerun = run_pipeline(
        settings,
        "2026-11-18",
        products=[PRODUCT_A, PRODUCT_B],
        source=source,
        db_path=db_path,
        report_dir=report_dir,
    )

    assert (day1.run_log.success, day1.run_log.skipped, day1.run_log.failed) == (2, 0, 0)
    assert (day2.run_log.success, day2.run_log.skipped, day2.run_log.failed) == (2, 0, 0)
    assert rerun.run_log.cache_hits == 2
    assert day2.report_html.exists()
    assert "Amazon" in day2.report_html.read_text(encoding="utf-8")
    assert "Razer Basilisk V3" in day2.report_html.read_text(encoding="utf-8")

    conn = store.connect(db_path)
    assert store.count_snapshots(conn) == 4
    assert store.count_analyses(conn) == 4
    assert store.find_duplicate_snapshots(conn) == []
    history = store.get_history(conn, PRODUCT_A.product_id, "2026-11-18")
    assert [item.price for item in history] == [34.99, 32.99]
    conn.close()


def test_pipeline_failure_isolation(tmp_path: Path) -> None:
    cache_dir = tmp_path / "raw"
    _cache(cache_dir, PRODUCT_A.product_id, "2026-11-18", render_page(price="$34.99"))
    _cache(cache_dir, PRODUCT_B.product_id, "2026-11-18", captcha_page())

    settings = Settings(llm_mode="mock")
    source = AmazonSource(cache_dir=cache_dir, mode="replay")
    result = run_pipeline(
        settings,
        "2026-11-18",
        products=[PRODUCT_A, PRODUCT_B, PRODUCT_C],
        source=source,
        db_path=tmp_path / "test.db",
        report_dir=tmp_path / "reports",
    )

    assert result.run_log.success == 1
    assert result.run_log.failed == 1
    assert result.run_log.skipped == 1
    assert result.run_log.blocked == 1
    details = {item["product_id"]: item for item in result.run_log.details}
    assert details[PRODUCT_A.product_id]["status"] == "success"
    assert details[PRODUCT_B.product_id]["status"] == "failed"
    assert details[PRODUCT_C.product_id]["status"] == "skipped"


def test_pipeline_writes_excel_copy(tmp_path: Path) -> None:
    cache_dir = tmp_path / "raw"
    _cache(cache_dir, PRODUCT_A.product_id, "2026-11-18", render_page(price="$32.99"))
    _cache(cache_dir, PRODUCT_B.product_id, "2026-11-18", render_page(
        title="Samsung T7 Portable SSD",
        price="$186.99",
        rating="4.7 out of 5 stars",
        reviews="(37,150 ratings)",
        sales="5K+ bought in past month",
    ))

    out_path = tmp_path / "collected.xlsx"
    settings = Settings(llm_mode="mock")
    source = AmazonSource(cache_dir=cache_dir, mode="replay")
    result = run_pipeline(
        settings,
        "2026-11-18",
        products=[PRODUCT_A, PRODUCT_B],
        source=source,
        db_path=tmp_path / "test.db",
        report_dir=tmp_path / "reports",
        write_excel=True,
        excel_path=EXCEL,
        excel_out=out_path,
    )

    assert result.excel_path == out_path
    workbook = load_workbook(out_path)
    sheet = workbook[PRODUCT_A.excel_sheet]
    dates = [sheet.cell(row=row, column=10).value for row in range(2, sheet.max_row + 1)]
    assert any(value is not None and str(value).startswith("2026-11-18") for value in dates)
    row = sheet.max_row
    assert sheet.cell(row=row, column=6).value == "$32.99"

    source_sheet = workbook["商品数据"]
    assert source_sheet.max_row >= 2
