from __future__ import annotations

from pathlib import Path

from app import store
from app.config import Settings
from app.demo_runner import run_demo_pipeline
from app.stats import build_stats, render_stats

PROJECT = Path(__file__).resolve().parents[1]
DEMO = PROJECT / "data" / "demo" / "snapshots.json"
EXCEL = PROJECT / "data" / "source" / "amazon_products.xlsx"


def test_stats_counts_and_missing_fields(tmp_path: Path) -> None:
    settings = Settings(llm_mode="mock")
    run_demo_pipeline(
        settings,
        demo_path=DEMO,
        db_path=tmp_path / "demo.db",
        report_dir=tmp_path / "reports",
        excel_path=EXCEL,
        excel_out=tmp_path / "demo.xlsx",
    )
    conn = store.connect(tmp_path / "demo.db")
    stats = build_stats(conn)
    conn.close()

    assert stats["snapshots"] == 11
    assert stats["analyses"] == 4
    assert stats["missing"]["price"]["count"] == 3
    assert stats["missing"]["sales"]["count"] == 2
    assert stats["runs"]["total"] == 1
    assert stats["runs"]["success"] == 4
    assert 0 <= stats["runs"]["cache_hit_rate"] <= 100
    assert "字段缺失率" in render_stats(stats)
