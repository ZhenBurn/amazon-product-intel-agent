"""Offline real-snapshot demo data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.models import Product, Snapshot

DEFAULT_DEMO_PATH = Path("data/demo/snapshots.json")


@dataclass
class DemoData:
    products: list[Product]
    snapshots: list[Snapshot]
    meta: dict

    @property
    def captured_at(self) -> str:
        value = self.meta.get("captured_at")
        if value:
            return str(value)
        return max(snapshot.snapshot_date for snapshot in self.snapshots)

    def current_snapshots(self) -> list[Snapshot]:
        date = self.captured_at
        return [
            snapshot for snapshot in self.snapshots if snapshot.snapshot_date == date
        ]

    def history(self, product_id: str, up_to_date: str, limit: int = 5) -> list[Snapshot]:
        rows = [
            snapshot
            for snapshot in self.snapshots
            if snapshot.product_id == product_id and snapshot.snapshot_date <= up_to_date
        ]
        rows.sort(key=lambda snapshot: snapshot.snapshot_date)
        return rows[-limit:]


def load_demo(path: Path | None = None) -> DemoData:
    demo_path = path or DEFAULT_DEMO_PATH
    payload = json.loads(demo_path.read_text(encoding="utf-8"))
    products = [Product.model_validate(item) for item in payload.get("products", [])]
    snapshots = [Snapshot.model_validate(item) for item in payload.get("snapshots", [])]
    if not products or not snapshots:
        raise ValueError(f"demo snapshot is empty: {demo_path}")
    return DemoData(products=products, snapshots=snapshots, meta=payload.get("meta", {}))
