"""Export sanitized real snapshots for the offline portfolio demo."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app import store
from app.models import Product, Snapshot

DEFAULT_DB = Path("data/runtime/product_intel.db")
DEFAULT_OUT = Path("data/demo/snapshots.json")
TEXT_LIMIT = 320


def _short(text: str | None, limit: int = TEXT_LIMIT) -> str | None:
    if not text:
        return None
    cleaned = " ".join(text.split())
    return cleaned if len(cleaned) <= limit else cleaned[:limit].rstrip() + "…"


def _sanitize(snapshot: Snapshot) -> Snapshot:
    data = snapshot.model_dump()
    data["bullets"] = [_short(item, 240) or "" for item in snapshot.bullets[:2]]
    data["description"] = _short(snapshot.description)
    data["gallery_images"] = snapshot.gallery_images[:4]
    data["raw_html_path"] = None
    data["selector_hits"] = {}
    return Snapshot.model_validate(data)


def _dump_product(product: Product) -> dict:
    return product.model_dump()


def main() -> None:
    conn = store.connect(DEFAULT_DB)
    try:
        store.init_db(conn)
        products = store.list_products(conn)
        dates = [
            row["snapshot_date"]
            for row in conn.execute(
                "SELECT DISTINCT snapshot_date FROM snapshots ORDER BY snapshot_date"
            ).fetchall()
        ]
        snapshots: list[Snapshot] = []
        for snapshot_date in dates:
            snapshots.extend(store.list_snapshots(conn, snapshot_date))
    finally:
        conn.close()

    if not products or not snapshots:
        raise SystemExit("no data in product_intel.db; run demo or import-excel first")

    captured_at = max(snapshot.snapshot_date for snapshot in snapshots)
    payload = {
        "meta": {
            "captured_at": captured_at,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source": "real Amazon pages, extracted fields only",
            "note": (
                "Raw HTML is not committed. This is a real snapshot stored for "
                "the offline portfolio demo."
            ),
            "snapshots": len(snapshots),
            "products": len(products),
        },
        "products": [_dump_product(product) for product in products],
        "snapshots": [_sanitize(snapshot).model_dump() for snapshot in snapshots],
    }

    DEFAULT_OUT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {DEFAULT_OUT}: {len(products)} products, "
        f"{len(snapshots)} snapshots, captured_at={captured_at}"
    )


if __name__ == "__main__":
    main()
