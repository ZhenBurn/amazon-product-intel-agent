from __future__ import annotations

import json
from pathlib import Path

from bs4 import BeautifulSoup

from app import store
from app.config import Settings
from app.demo_runner import run_demo_pipeline

PROJECT = Path(__file__).resolve().parents[1]
DEMO = PROJECT / "data" / "demo" / "snapshots.json"
EXCEL = PROJECT / "data" / "source" / "amazon_products.xlsx"


def test_demo_snapshot_is_real_and_sanitized() -> None:
    payload = json.loads(DEMO.read_text(encoding="utf-8"))
    assert payload["meta"]["captured_at"] == "2026-11-18"
    assert payload["meta"]["snapshots"] == 11
    assert len(payload["products"]) == 4
    assert all(len(snapshot["gallery_images"]) <= 4 for snapshot in payload["snapshots"])
    assert all(len(snapshot["bullets"]) <= 2 for snapshot in payload["snapshots"])
    assert all(snapshot["raw_html_path"] is None for snapshot in payload["snapshots"])


def test_offline_demo_runs_without_cache(tmp_path: Path) -> None:
    settings = Settings(llm_mode="mock")
    out_excel = tmp_path / "demo.xlsx"
    result = run_demo_pipeline(
        settings,
        demo_path=DEMO,
        db_path=tmp_path / "demo.db",
        report_dir=tmp_path / "reports",
        excel_path=EXCEL,
        excel_out=out_excel,
    )

    assert result.run_log.source_mode == "demo"
    assert result.run_log.success == 4
    assert result.run_log.skipped == 0
    assert result.run_log.failed == 0
    assert out_excel.exists()

    html = result.report_html.read_text(encoding="utf-8")
    assert "离线真实快照" in html
    assert "合成的 Amazon" not in html
    soup = BeautifulSoup(html, "html.parser")
    assert len(soup.select("article.card")) == 4

    conn = store.connect(tmp_path / "demo.db")
    assert store.count_snapshots(conn) == 11
    assert store.count_analyses(conn) == 4
    assert store.find_duplicate_snapshots(conn) == []
    history = store.get_history(conn, "B09C13PZX7", "2026-11-18")
    assert [item.snapshot_date for item in history] == [
        "2025-12-24",
        "2025-12-27",
        "2026-01-01",
        "2026-01-03",
        "2026-11-18",
    ]
    conn.close()


def test_offline_demo_is_idempotent(tmp_path: Path) -> None:
    settings = Settings(llm_mode="mock")
    kwargs = {
        "demo_path": DEMO,
        "db_path": tmp_path / "demo.db",
        "report_dir": tmp_path / "reports",
        "excel_path": EXCEL,
        "excel_out": tmp_path / "demo.xlsx",
    }
    first = run_demo_pipeline(settings, **kwargs)
    second = run_demo_pipeline(settings, **kwargs)

    assert first.run_log.success == second.run_log.success == 4
    conn = store.connect(tmp_path / "demo.db")
    assert store.count_snapshots(conn) == 11
    assert store.count_analyses(conn) == 4
    assert store.find_duplicate_snapshots(conn) == []
    conn.close()
