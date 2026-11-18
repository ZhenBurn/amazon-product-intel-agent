"""CLI entry points."""

from __future__ import annotations

import argparse
import json
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Sequence

from app import store
from app.config import Settings, get_settings
from app.demo_runner import run_demo_pipeline
from app.excel_io import load_watchlist, read_history, write_snapshots
from app.parse import parse_product_page
from app.pipeline import run_pipeline
from app.sources.amazon import AmazonSource
from app.stats import build_stats, render_stats


def _today() -> str:
    return datetime.now().astimezone().date().isoformat()


def _print_run(result) -> None:
    run = result.run_log
    print(
        f"{run.snapshot_date}: success={run.success} skipped={run.skipped} "
        f"failed={run.failed} blocked={run.blocked} cache_hits={run.cache_hits} "
        f"source={run.source_mode}"
    )
    print(f"report: {result.report_html}")
    if result.excel_path:
        print(f"excel:  {result.excel_path}")


def _build_source(settings: Settings, mode: str) -> AmazonSource:
    return AmazonSource(
        cache_dir=settings.raw_dir,
        mode=mode,
        marketplace=settings.amazon_marketplace,
        timeout=settings.amazon_timeout,
        retries=settings.amazon_retries,
        delay=settings.amazon_delay if mode == "live" else 0.0,
        proxy=settings.amazon_proxy,
        headless=settings.amazon_headless,
        user_agent=settings.amazon_user_agent,
    )


def sync_history(settings: Settings, db_path: Path, excel_path: Path) -> tuple[int, int]:
    products = load_watchlist(excel_path)
    snapshots = read_history(excel_path, products)
    conn = store.connect(db_path)
    try:
        store.init_db(conn)
        for product in products:
            store.upsert_product(conn, product)
        for snapshot in snapshots:
            store.upsert_snapshot(conn, snapshot)
        conn.commit()
        return len(products), len(snapshots)
    finally:
        conn.close()


def cmd_collect(args: argparse.Namespace) -> int:
    settings = get_settings()
    if args.source:
        settings = settings.model_copy(update={"amazon_source": args.source})
    excel_path = Path(args.excel)
    products = load_watchlist(excel_path)
    if args.asin:
        wanted = {asin.upper() for asin in args.asin}
        products = [product for product in products if product.product_id in wanted]
    if args.limit:
        products = products[: args.limit]
    if not products:
        print("no products selected")
        return 1

    result = run_pipeline(
        settings,
        args.date,
        products=products,
        source=_build_source(settings, settings.amazon_source),
        db_path=Path(args.db),
        report_dir=Path(args.report_dir),
        refresh=args.refresh,
        write_excel=not args.no_excel,
        excel_path=excel_path,
        excel_out=Path(args.excel_out),
        in_place=args.in_place,
    )
    _print_run(result)
    if args.open:
        webbrowser.open(result.report_html.resolve().as_uri())
    return 0


def cmd_import_excel(args: argparse.Namespace) -> int:
    settings = get_settings()
    products, snapshots = sync_history(
        settings,
        Path(args.db),
        Path(args.excel),
    )
    print(f"imported {products} products, {snapshots} unique snapshots")
    return 0


def cmd_export_excel(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    try:
        store.init_db(conn)
        snapshots = store.list_snapshots(conn, args.date)
    finally:
        conn.close()
    if not snapshots:
        print(f"no snapshots for {args.date}")
        return 1
    products = load_watchlist(Path(args.excel))
    result = write_snapshots(
        Path(args.excel),
        snapshots,
        products=products,
        out_path=Path(args.out),
        in_place=args.in_place,
    )
    print(
        f"excel: {result.path} appended={len(result.appended)} "
        f"updated={len(result.updated)} skipped={len(result.skipped)}"
    )
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    settings = get_settings()
    products = load_watchlist(Path(args.excel))
    product = next((item for item in products if item.product_id == args.asin.upper()), None)
    if product is None:
        print(f"unknown asin: {args.asin}")
        return 1
    source = _build_source(settings, "live")
    result = source.capture(product, args.date, Path(args.file))
    print(f"captured {product.product_id}@{args.date} -> {result.path}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    conn = store.connect(Path(args.db))
    try:
        store.init_db(conn)
        stats = build_stats(conn)
    finally:
        conn.close()
    if args.json:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    else:
        print(render_stats(stats), end="")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    settings = get_settings()
    source = _build_source(settings, "replay")
    products = load_watchlist(Path(args.excel))
    total = 0
    failed = 0
    for product in products:
        dates = [args.date] if args.date else source.cached_dates(product.product_id)
        if not dates:
            print(f"{product.product_id}: no cache")
            continue
        for snapshot_date in dates:
            total += 1
            try:
                fetched = source.fetch(product, snapshot_date)
                parsed = parse_product_page(fetched.html)
                hits = ", ".join(sorted(parsed.selector_hits))
                print(f"{product.product_id}@{snapshot_date}: ok [{hits}]")
            except Exception as exc:
                failed += 1
                print(f"{product.product_id}@{snapshot_date}: FAIL {exc}")
    print(f"verified {total - failed}/{total}")
    return 0 if failed == 0 else 1


def cmd_demo(args: argparse.Namespace) -> int:
    settings = get_settings()
    settings = settings.model_copy(update={"amazon_source": "replay"})
    excel_path = Path(args.excel)
    db_path = Path(args.db)
    products = load_watchlist(excel_path)
    source = _build_source(settings, "replay")
    dates = [
        date for product in products for date in source.cached_dates(product.product_id)
    ]

    if not dates:
        demo_path = Path(args.demo_data)
        if not demo_path.exists():
            print(
                "no cached Amazon pages and no offline demo snapshot. "
                "Capture real pages first:\n"
                "  uv run python -m app.cli capture "
                "--asin B09C13PZX7 --date 2026-11-18 --file page.html"
            )
            return 1
        print(f"offline demo: {demo_path}")
        result = run_demo_pipeline(
            settings,
            demo_path=demo_path,
            db_path=db_path,
            report_dir=Path(args.report_dir),
            excel_path=excel_path,
            excel_out=Path(args.excel_out),
            write_excel=not args.no_excel,
        )
        _print_run(result)
        if not args.no_open:
            webbrowser.open(result.report_html.resolve().as_uri())
        return 0

    if not db_path.exists():
        product_count, snapshot_count = sync_history(settings, db_path, excel_path)
        print(f"history: {product_count} products, {snapshot_count} snapshots")

    snapshot_date = args.date or max(dates)
    result = run_pipeline(
        settings,
        snapshot_date,
        products=products,
        source=source,
        db_path=db_path,
        report_dir=Path(args.report_dir),
        write_excel=not args.no_excel,
        excel_path=excel_path,
        excel_out=Path(args.excel_out),
    )
    _print_run(result)
    if not args.no_open:
        webbrowser.open(result.report_html.resolve().as_uri())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Amazon product intel agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="Fetch products and write a report")
    collect.add_argument("--date", default=_today())
    collect.add_argument("--source", choices=["replay", "live"], default=None)
    collect.add_argument("--asin", action="append", default=[])
    collect.add_argument("--limit", type=int, default=0)
    collect.add_argument("--refresh", action="store_true")
    collect.add_argument("--excel", default="data/source/amazon_products.xlsx")
    collect.add_argument("--excel-out", default="data/exports/amazon_products.xlsx")
    collect.add_argument("--in-place", action="store_true")
    collect.add_argument("--no-excel", action="store_true")
    collect.add_argument("--db", default="data/runtime/product_intel.db")
    collect.add_argument("--report-dir", default="reports")
    collect.add_argument("--open", action="store_true")
    collect.set_defaults(func=cmd_collect)

    replay = subparsers.add_parser("replay", help="Replay cached HTML without network")
    replay.add_argument("--date", default=_today())
    replay.add_argument("--asin", action="append", default=[])
    replay.add_argument("--limit", type=int, default=0)
    replay.add_argument("--excel", default="data/source/amazon_products.xlsx")
    replay.add_argument("--excel-out", default="data/exports/amazon_products.xlsx")
    replay.add_argument("--in-place", action="store_true")
    replay.add_argument("--no-excel", action="store_true")
    replay.add_argument("--db", default="data/runtime/product_intel.db")
    replay.add_argument("--report-dir", default="reports")
    replay.add_argument("--open", action="store_true")
    replay.set_defaults(
        func=lambda args: cmd_collect(
            argparse.Namespace(**{**vars(args), "source": "replay", "refresh": False})
        )
    )

    demo = subparsers.add_parser(
        "demo",
        help="Replay the latest cache, or use the committed offline snapshot",
    )
    demo.add_argument("--date", default="")
    demo.add_argument("--excel", default="data/source/amazon_products.xlsx")
    demo.add_argument("--excel-out", default="data/exports/amazon_products.xlsx")
    demo.add_argument("--demo-data", default="data/demo/snapshots.json")
    demo.add_argument("--no-excel", action="store_true")
    demo.add_argument("--db", default="data/runtime/product_intel.db")
    demo.add_argument("--report-dir", default="reports")
    demo.add_argument("--no-open", action="store_true")
    demo.set_defaults(func=cmd_demo)

    import_excel = subparsers.add_parser("import-excel", help="Import workbook history")
    import_excel.add_argument("--excel", default="data/source/amazon_products.xlsx")
    import_excel.add_argument("--db", default="data/runtime/product_intel.db")
    import_excel.set_defaults(func=cmd_import_excel)

    export_excel = subparsers.add_parser("export-excel", help="Write stored snapshots to Excel")
    export_excel.add_argument("--date", required=True)
    export_excel.add_argument("--excel", default="data/source/amazon_products.xlsx")
    export_excel.add_argument("--out", default="data/exports/amazon_products.xlsx")
    export_excel.add_argument("--in-place", action="store_true")
    export_excel.add_argument("--db", default="data/runtime/product_intel.db")
    export_excel.set_defaults(func=cmd_export_excel)

    capture = subparsers.add_parser("capture", help="Import a manually saved Amazon HTML page")
    capture.add_argument("--asin", required=True)
    capture.add_argument("--date", default=_today())
    capture.add_argument("--file", required=True)
    capture.add_argument("--excel", default="data/source/amazon_products.xlsx")
    capture.set_defaults(func=cmd_capture)

    verify = subparsers.add_parser("verify", help="Re-parse cached pages and check selectors")
    verify.add_argument("--date", default="")
    verify.add_argument("--excel", default="data/source/amazon_products.xlsx")
    verify.set_defaults(func=cmd_verify)

    stats = subparsers.add_parser("stats", help="Show data-quality and run statistics")
    stats.add_argument("--db", default="data/runtime/product_intel.db")
    stats.add_argument("--json", action="store_true")
    stats.set_defaults(func=cmd_stats)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
