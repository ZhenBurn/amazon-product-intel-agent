"""Generate a full report from the committed offline snapshot."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app import store
from app.config import Settings
from app.demo_data import DEFAULT_DEMO_PATH, DemoData, load_demo
from app.excel_io import write_snapshots
from app.llm import AnalysisClient, MockAnalysisClient
from app.models import Product, RunLog, Snapshot
from app.pipeline import PipelineResult
from app.report import write_reports


def run_demo_pipeline(
    settings: Settings,
    demo_path: Path | None = None,
    db_path: Path | None = None,
    report_dir: Path | None = None,
    excel_path: Path | None = None,
    excel_out: Path | None = None,
    write_excel: bool = True,
    in_place: bool = False,
    llm_client: AnalysisClient | None = None,
) -> PipelineResult:
    """Seed demo snapshots into SQLite, analyze the latest date, and render reports."""
    db_path = db_path or settings.db_path
    report_dir = report_dir or settings.report_dir
    excel_path = excel_path or settings.excel_path
    demo: DemoData = load_demo(demo_path or DEFAULT_DEMO_PATH)
    products = demo.products
    snapshot_date = demo.captured_at
    current = {snapshot.product_id: snapshot for snapshot in demo.current_snapshots()}
    llm = llm_client or MockAnalysisClient()

    conn = store.connect(db_path)
    try:
        store.init_db(conn)
        for product in products:
            store.upsert_product(conn, product)
        for snapshot in demo.snapshots:
            store.upsert_snapshot(conn, snapshot)
        conn.commit()

        run_id = str(uuid4())
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()
        details: list[dict] = []
        analyses = 0
        collected: list[Snapshot] = []

        for product in products:
            snapshot = current.get(product.product_id)
            if snapshot is None:
                details.append(
                    {
                        "product_id": product.product_id,
                        "status": "skipped",
                        "error": "demo snapshot missing for product",
                        "data_gaps": ["demo"],
                    }
                )
                continue
            history = store.get_history(
                conn,
                product.product_id,
                snapshot_date,
                limit=5,
            )
            analysis = llm.analyze(_product_payload(product), snapshot, history)
            store.upsert_analysis(conn, analysis)
            collected.append(snapshot)
            analyses += 1
            details.append(
                {
                    "product_id": product.product_id,
                    "status": "success",
                    "title": snapshot.title,
                    "price": snapshot.price,
                    "sales_text": snapshot.sales_text,
                    "data_gaps": snapshot.data_gaps,
                    "confidence": analysis.confidence,
                    "source": "demo",
                    "from_cache": True,
                    "raw_html": None,
                }
            )
        conn.commit()

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        run_log = RunLog(
            run_id=run_id,
            snapshot_date=snapshot_date,
            started_at=started_at,
            duration_ms=duration_ms,
            total=len(products),
            success=analyses,
            skipped=len(products) - analyses,
            failed=0,
            source_mode="demo",
            blocked=0,
            cache_hits=0,
            details=details,
        )
        store.insert_run_log(
            conn,
            run_log.run_id,
            run_log.snapshot_date,
            run_log.started_at,
            run_log.duration_ms,
            run_log.total,
            run_log.success,
            run_log.skipped,
            run_log.failed,
            run_log.details,
            source_mode=run_log.source_mode,
            blocked=run_log.blocked,
            cache_hits=run_log.cache_hits,
        )
        conn.commit()

        report_md, report_html = write_reports(conn, run_log, report_dir, products)
        output_excel: Path | None = None
        if write_excel and collected:
            written = write_snapshots(
                excel_path,
                collected,
                products=products,
                out_path=excel_out or settings.excel_out,
                in_place=in_place,
            )
            output_excel = written.path
        return PipelineResult(
            run_log=run_log,
            report_md=report_md,
            report_html=report_html,
            excel_path=output_excel,
        )
    finally:
        conn.close()


def _product_payload(product: Product) -> dict:
    return {
        "name": product.name,
        "asin": product.product_id,
        "url": product.url,
        "category": product.category,
    }
