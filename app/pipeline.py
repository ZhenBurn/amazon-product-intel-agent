"""Pipeline: fetch -> parse -> normalize -> validate -> store -> analyze -> report."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from app import store
from app.config import Settings
from app.errors import (
    BlockedError,
    CacheMissError,
    FetchError,
    PageUnavailableError,
    ParseError,
    SourceBlockedError,
    SourceUnavailableError,
)
from app.excel_io import load_watchlist, write_snapshots
from app.llm import AnalysisClient, build_analysis_client
from app.models import Product, RunLog, Snapshot
from app.normalize import build_snapshot
from app.parse import parse_product_page
from app.report import write_reports
from app.sources.amazon import AmazonSource


@dataclass
class PipelineResult:
    run_log: RunLog
    report_md: Path
    report_html: Path
    excel_path: Path | None = None


def run_pipeline(
    settings: Settings,
    snapshot_date: str,
    products: list[Product] | None = None,
    source: AmazonSource | None = None,
    db_path: Path | None = None,
    report_dir: Path | None = None,
    llm_client: AnalysisClient | None = None,
    refresh: bool = False,
    write_excel: bool = False,
    excel_path: Path | None = None,
    excel_out: Path | None = None,
    in_place: bool = False,
) -> PipelineResult:
    db_path = db_path or settings.db_path
    report_dir = report_dir or settings.report_dir
    excel_path = excel_path or settings.excel_path
    llm = llm_client or build_analysis_client(settings)

    if products is None:
        products = load_watchlist(excel_path)
    if source is None:
        source = AmazonSource(
            cache_dir=settings.raw_dir,
            mode=settings.amazon_source,
            marketplace=settings.amazon_marketplace,
            timeout=settings.amazon_timeout,
            retries=settings.amazon_retries,
            delay=settings.amazon_delay if settings.amazon_source == "live" else 0.0,
            proxy=settings.amazon_proxy,
            headless=settings.amazon_headless,
            user_agent=settings.amazon_user_agent,
        )

    conn = store.connect(db_path)
    try:
        store.init_db(conn)
        for product in products:
            store.upsert_product(conn, product)
        conn.commit()

        run_id = str(uuid4())
        started_at = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()
        details: list[dict[str, Any]] = []
        collected: list[Snapshot] = []
        success = 0
        skipped = 0
        failed = 0
        blocked = 0
        cache_hits = 0

        for product in products:
            try:
                fetched = source.fetch(product, snapshot_date, refresh=refresh)
                if fetched.from_cache:
                    cache_hits += 1
                parsed = parse_product_page(fetched.html)
                snapshot = build_snapshot(
                    product,
                    snapshot_date,
                    parsed,
                    raw_html_path=str(fetched.path),
                )
                store.upsert_snapshot(conn, snapshot)
                history = store.get_history(
                    conn,
                    product.product_id,
                    snapshot_date,
                    limit=5,
                )
                analysis = llm.analyze(
                    {
                        "name": product.name,
                        "asin": product.product_id,
                        "url": product.url,
                        "category": product.category,
                    },
                    snapshot,
                    history,
                )
                store.upsert_analysis(conn, analysis)
                collected.append(snapshot)
                success += 1
                details.append(
                    {
                        "product_id": product.product_id,
                        "status": "success",
                        "title": snapshot.title,
                        "price": snapshot.price,
                        "sales_text": snapshot.sales_text,
                        "data_gaps": snapshot.data_gaps,
                        "confidence": analysis.confidence,
                        "source": fetched.source,
                        "from_cache": fetched.from_cache,
                        "raw_html": str(fetched.path),
                    }
                )
                conn.commit()
            except (SourceBlockedError, BlockedError) as exc:
                blocked += 1
                failed += 1
                details.append(
                    {
                        "product_id": product.product_id,
                        "status": "failed",
                        "error": f"采集被拦截：{exc}",
                        "blocked": True,
                    }
                )
                conn.rollback()
            except CacheMissError as exc:
                skipped += 1
                details.append(
                    {
                        "product_id": product.product_id,
                        "status": "skipped",
                        "error": f"无可用缓存：{exc}",
                        "data_gaps": ["缓存"],
                    }
                )
                conn.rollback()
            except (SourceUnavailableError, PageUnavailableError) as exc:
                skipped += 1
                details.append(
                    {
                        "product_id": product.product_id,
                        "status": "skipped",
                        "error": f"页面不可用：{exc}",
                        "data_gaps": ["页面"],
                    }
                )
                conn.rollback()
            except (ParseError, FetchError) as exc:
                failed += 1
                details.append(
                    {
                        "product_id": product.product_id,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                conn.rollback()
            except Exception as exc:  # isolate per-product failures
                failed += 1
                details.append(
                    {
                        "product_id": product.product_id,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                conn.rollback()

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        run_log = RunLog(
            run_id=run_id,
            snapshot_date=snapshot_date,
            started_at=started_at,
            duration_ms=duration_ms,
            total=len(products),
            success=success,
            skipped=skipped,
            failed=failed,
            source_mode=source.mode,
            blocked=blocked,
            cache_hits=cache_hits,
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
