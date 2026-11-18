"""SQLite persistence for products, snapshots, analyses, and run logs."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import Product, ProductAnalysis, Snapshot

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    marketplace TEXT NOT NULL DEFAULT 'amazon.com',
    excel_sheet TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS snapshots (
    product_id TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    title TEXT NOT NULL,
    price REAL,
    list_price REAL,
    currency TEXT,
    rating REAL,
    reviews INTEGER,
    sales_value INTEGER,
    sales_text TEXT,
    bullets_json TEXT NOT NULL DEFAULT '[]',
    description TEXT,
    main_image TEXT,
    gallery_json TEXT NOT NULL DEFAULT '[]',
    in_stock INTEGER,
    availability TEXT,
    seller TEXT,
    coupon TEXT,
    data_gaps_json TEXT NOT NULL,
    raw_html_path TEXT,
    selector_hits_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    PRIMARY KEY (product_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS analyses (
    product_id TEXT NOT NULL,
    snapshot_date TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    price_trend TEXT NOT NULL,
    sales_trend TEXT NOT NULL,
    key_changes_json TEXT NOT NULL,
    actions_json TEXT NOT NULL,
    confidence TEXT NOT NULL,
    data_gaps_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (product_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS run_logs (
    run_id TEXT PRIMARY KEY,
    snapshot_date TEXT NOT NULL,
    started_at TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    total INTEGER NOT NULL,
    success INTEGER NOT NULL,
    skipped INTEGER NOT NULL,
    failed INTEGER NOT NULL,
    source_mode TEXT NOT NULL DEFAULT 'replay',
    blocked INTEGER NOT NULL DEFAULT 0,
    cache_hits INTEGER NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_date ON snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_analyses_date ON analyses(snapshot_date);
"""

MIGRATIONS: dict[str, dict[str, str]] = {
    "products": {
        "url": "TEXT NOT NULL DEFAULT ''",
        "marketplace": "TEXT NOT NULL DEFAULT 'amazon.com'",
        "excel_sheet": "TEXT NOT NULL DEFAULT ''",
    },
    "snapshots": {
        "list_price": "REAL",
        "bullets_json": "TEXT NOT NULL DEFAULT '[]'",
        "main_image": "TEXT",
        "gallery_json": "TEXT NOT NULL DEFAULT '[]'",
        "in_stock": "INTEGER",
        "availability": "TEXT",
        "seller": "TEXT",
        "coupon": "TEXT",
        "raw_html_path": "TEXT",
        "selector_hits_json": "TEXT NOT NULL DEFAULT '{}'",
    },
    "run_logs": {
        "source_mode": "TEXT NOT NULL DEFAULT 'replay'",
        "blocked": "INTEGER NOT NULL DEFAULT 0",
        "cache_hits": "INTEGER NOT NULL DEFAULT 0",
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _migrate(conn: sqlite3.Connection) -> None:
    for table, columns in MIGRATIONS.items():
        existing = _table_columns(conn, table)
        if not existing:
            continue
        for column, definition in columns.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    conn.execute("PRAGMA user_version = 2")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()


def upsert_product(conn: sqlite3.Connection, product: Product) -> None:
    columns = _table_columns(conn, "products")
    if "path" in columns:
        conn.execute(
            """
            INSERT INTO products (
                product_id, name, category, url, marketplace, excel_sheet, path
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(product_id) DO UPDATE SET
                name = excluded.name,
                category = excluded.category,
                url = excluded.url,
                marketplace = excluded.marketplace,
                excel_sheet = excluded.excel_sheet,
                path = excluded.path
            """,
            (
                product.product_id,
                product.name,
                product.category,
                product.url,
                product.marketplace,
                product.excel_sheet,
                product.url,
            ),
        )
        return
    conn.execute(
        """
        INSERT INTO products (
            product_id, name, category, url, marketplace, excel_sheet
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(product_id) DO UPDATE SET
            name = excluded.name,
            category = excluded.category,
            url = excluded.url,
            marketplace = excluded.marketplace,
            excel_sheet = excluded.excel_sheet
        """,
        (
            product.product_id,
            product.name,
            product.category,
            product.url,
            product.marketplace,
            product.excel_sheet,
        ),
    )


def upsert_snapshot(conn: sqlite3.Connection, snapshot: Snapshot) -> None:
    conn.execute(
        """
        INSERT INTO snapshots (
            product_id, snapshot_date, title, price, list_price, currency,
            rating, reviews, sales_value, sales_text, bullets_json, description,
            main_image, gallery_json, in_stock, availability, seller, coupon,
            data_gaps_json, raw_html_path, selector_hits_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(product_id, snapshot_date) DO UPDATE SET
            title = excluded.title,
            price = excluded.price,
            list_price = excluded.list_price,
            currency = excluded.currency,
            rating = excluded.rating,
            reviews = excluded.reviews,
            sales_value = excluded.sales_value,
            sales_text = excluded.sales_text,
            bullets_json = excluded.bullets_json,
            description = excluded.description,
            main_image = excluded.main_image,
            gallery_json = excluded.gallery_json,
            in_stock = excluded.in_stock,
            availability = excluded.availability,
            seller = excluded.seller,
            coupon = excluded.coupon,
            data_gaps_json = excluded.data_gaps_json,
            raw_html_path = excluded.raw_html_path,
            selector_hits_json = excluded.selector_hits_json,
            created_at = excluded.created_at
        """,
        (
            snapshot.product_id,
            snapshot.snapshot_date,
            snapshot.title,
            snapshot.price,
            snapshot.list_price,
            snapshot.currency,
            snapshot.rating,
            snapshot.reviews,
            snapshot.sales_value,
            snapshot.sales_text,
            json.dumps(snapshot.bullets, ensure_ascii=False),
            snapshot.description,
            snapshot.main_image,
            json.dumps(snapshot.gallery_images, ensure_ascii=False),
            None if snapshot.in_stock is None else int(snapshot.in_stock),
            snapshot.availability,
            snapshot.seller,
            snapshot.coupon,
            json.dumps(snapshot.data_gaps, ensure_ascii=False),
            snapshot.raw_html_path,
            json.dumps(snapshot.selector_hits, ensure_ascii=False),
            _now(),
        ),
    )


def upsert_analysis(conn: sqlite3.Connection, analysis: ProductAnalysis) -> None:
    conn.execute(
        """
        INSERT INTO analyses (
            product_id, snapshot_date, title, summary, price_trend, sales_trend,
            key_changes_json, actions_json, confidence, data_gaps_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(product_id, snapshot_date) DO UPDATE SET
            title = excluded.title,
            summary = excluded.summary,
            price_trend = excluded.price_trend,
            sales_trend = excluded.sales_trend,
            key_changes_json = excluded.key_changes_json,
            actions_json = excluded.actions_json,
            confidence = excluded.confidence,
            data_gaps_json = excluded.data_gaps_json,
            created_at = excluded.created_at
        """,
        (
            analysis.product_id,
            analysis.snapshot_date,
            analysis.title,
            analysis.summary,
            analysis.price_trend,
            analysis.sales_trend,
            json.dumps(analysis.key_changes, ensure_ascii=False),
            json.dumps(analysis.actions, ensure_ascii=False),
            analysis.confidence,
            json.dumps(analysis.data_gaps, ensure_ascii=False),
            _now(),
        ),
    )


def _json_list(value: Any) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _json_dict(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _row_to_snapshot(row: sqlite3.Row) -> Snapshot:
    return Snapshot(
        product_id=row["product_id"],
        snapshot_date=row["snapshot_date"],
        title=row["title"],
        price=row["price"],
        list_price=row["list_price"],
        currency=row["currency"],
        rating=row["rating"],
        reviews=row["reviews"],
        sales_value=row["sales_value"],
        sales_text=row["sales_text"],
        bullets=_json_list(row["bullets_json"]),
        description=row["description"],
        main_image=row["main_image"],
        gallery_images=_json_list(row["gallery_json"]),
        in_stock=None if row["in_stock"] is None else bool(row["in_stock"]),
        availability=row["availability"],
        seller=row["seller"],
        coupon=row["coupon"],
        data_gaps=_json_list(row["data_gaps_json"]),
        raw_html_path=row["raw_html_path"],
        selector_hits=_json_dict(row["selector_hits_json"]),
    )


def _row_to_analysis(row: sqlite3.Row) -> ProductAnalysis:
    return ProductAnalysis(
        product_id=row["product_id"],
        snapshot_date=row["snapshot_date"],
        title=row["title"],
        summary=row["summary"],
        price_trend=row["price_trend"],
        sales_trend=row["sales_trend"],
        key_changes=_json_list(row["key_changes_json"]),
        actions=_json_list(row["actions_json"]),
        confidence=row["confidence"],
        data_gaps=_json_list(row["data_gaps_json"]),
    )


def get_history(
    conn: sqlite3.Connection,
    product_id: str,
    up_to_date: str,
    limit: int = 5,
) -> list[Snapshot]:
    rows = conn.execute(
        """
        SELECT * FROM snapshots
        WHERE product_id = ? AND snapshot_date <= ?
        ORDER BY snapshot_date DESC
        LIMIT ?
        """,
        (product_id, up_to_date, limit),
    ).fetchall()
    return [_row_to_snapshot(row) for row in reversed(rows)]


def list_products(conn: sqlite3.Connection) -> list[Product]:
    rows = conn.execute(
        "SELECT * FROM products ORDER BY product_id"
    ).fetchall()
    return [
        Product(
            product_id=row["product_id"],
            name=row["name"],
            category=row["category"],
            url=row["url"],
            marketplace=row["marketplace"],
            excel_sheet=row["excel_sheet"],
        )
        for row in rows
    ]


def list_snapshots(conn: sqlite3.Connection, snapshot_date: str) -> list[Snapshot]:
    rows = conn.execute(
        "SELECT * FROM snapshots WHERE snapshot_date = ? ORDER BY product_id",
        (snapshot_date,),
    ).fetchall()
    return [_row_to_snapshot(row) for row in rows]


def list_analyses(conn: sqlite3.Connection, snapshot_date: str) -> list[ProductAnalysis]:
    rows = conn.execute(
        "SELECT * FROM analyses WHERE snapshot_date = ? ORDER BY product_id",
        (snapshot_date,),
    ).fetchall()
    return [_row_to_analysis(row) for row in rows]


def insert_run_log(
    conn: sqlite3.Connection,
    run_id: str,
    snapshot_date: str,
    started_at: str,
    duration_ms: float,
    total: int,
    success: int,
    skipped: int,
    failed: int,
    details: list[dict[str, Any]],
    source_mode: str = "replay",
    blocked: int = 0,
    cache_hits: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO run_logs (
            run_id, snapshot_date, started_at, duration_ms, total, success,
            skipped, failed, source_mode, blocked, cache_hits, details_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            snapshot_date,
            started_at,
            duration_ms,
            total,
            success,
            skipped,
            failed,
            source_mode,
            blocked,
            cache_hits,
            json.dumps(details, ensure_ascii=False),
        ),
    )


def count_snapshots(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0])


def count_analyses(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0])


def find_duplicate_snapshots(conn: sqlite3.Connection) -> list[tuple[str, str, int]]:
    rows = conn.execute(
        """
        SELECT product_id, snapshot_date, COUNT(*) AS count
        FROM snapshots
        GROUP BY product_id, snapshot_date
        HAVING count > 1
        """
    ).fetchall()
    return [(row["product_id"], row["snapshot_date"], row["count"]) for row in rows]
