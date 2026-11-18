"""Operational and data-quality statistics from SQLite."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from statistics import median
from typing import Any

MISSING_FIELDS = [
    ("price", "price IS NULL"),
    ("list_price", "list_price IS NULL"),
    ("rating", "rating IS NULL"),
    ("reviews", "reviews IS NULL"),
    ("sales", "sales_value IS NULL"),
    ("main_image", "main_image IS NULL OR main_image = ''"),
    ("bullets", "bullets_json = '[]'"),
    ("description", "description IS NULL OR description = ''"),
    ("seller", "seller IS NULL OR seller = ''"),
    ("gallery", "gallery_json = '[]'"),
]


def _percent(value: int, total: int) -> float:
    return round(value / total * 100, 1) if total else 0.0


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * ratio) - 1))
    return round(ordered[index], 2)


def build_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    snapshots = int(conn.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0])
    analyses = int(conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0])

    missing: dict[str, dict[str, float]] = {}
    for name, condition in MISSING_FIELDS:
        count = int(
            conn.execute(
                f"SELECT COUNT(*) FROM snapshots WHERE {condition}"
            ).fetchone()[0]
        )
        missing[name] = {"count": count, "rate": _percent(count, snapshots)}

    run = conn.execute(
        """
        SELECT COUNT(*) AS runs, COALESCE(SUM(success), 0) AS success,
               COALESCE(SUM(skipped), 0) AS skipped,
               COALESCE(SUM(failed), 0) AS failed,
               COALESCE(SUM(blocked), 0) AS blocked,
               COALESCE(SUM(cache_hits), 0) AS cache_hits
        FROM run_logs
        """
    ).fetchone()
    durations = [
        float(row[0])
        for row in conn.execute("SELECT duration_ms FROM run_logs").fetchall()
    ]
    selector_counts: Counter[str] = Counter()
    for row in conn.execute("SELECT selector_hits_json FROM snapshots").fetchall():
        try:
            hits = json.loads(row[0] or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(hits, dict):
            selector_counts.update(hits.keys())

    total_runs = int(run["runs"] or 0)
    attempts = int(run["success"]) + int(run["skipped"]) + int(run["failed"])
    return {
        "snapshots": snapshots,
        "analyses": analyses,
        "runs": {
            "total": total_runs,
            "success": int(run["success"]),
            "skipped": int(run["skipped"]),
            "failed": int(run["failed"]),
            "blocked": int(run["blocked"]),
            "cache_hits": int(run["cache_hits"]),
            "cache_hit_rate": _percent(int(run["cache_hits"]), attempts),
            "p50_ms": median(durations) if durations else 0.0,
            "p95_ms": _percentile(durations, 0.95),
        },
        "missing": missing,
        "selector_hits": dict(selector_counts.most_common()),
        "latest_snapshot_date": (
            conn.execute("SELECT MAX(snapshot_date) FROM snapshots").fetchone()[0]
        ),
    }


def render_stats(stats: dict[str, Any]) -> str:
    lines = [
        "# 数据质量与运行统计",
        "",
        f"- 快照：{stats['snapshots']}；分析：{stats['analyses']}；"
        f"最新日期：{stats['latest_snapshot_date'] or '—'}",
        f"- 运行：{stats['runs']['total']}；成功 {stats['runs']['success']}；"
        f"跳过 {stats['runs']['skipped']}；失败 {stats['runs']['failed']}；"
        f"被拦截 {stats['runs']['blocked']}；缓存命中率 {stats['runs']['cache_hit_rate']}%",
        f"- 耗时：p50 {stats['runs']['p50_ms']:.0f} ms；"
        f"p95 {stats['runs']['p95_ms']:.0f} ms",
        "",
        "## 字段缺失率",
        "",
        "| 字段 | 缺失数 | 缺失率 |",
        "| --- | --- | --- |",
    ]
    for name, value in stats["missing"].items():
        lines.append(f"| {name} | {value['count']} | {value['rate']}% |")
    lines.extend(["", "## 选择器命中", "", "| 字段 | 次数 |", "| --- | --- |"])
    for name, count in stats["selector_hits"].items():
        lines.append(f"| {name} | {count} |")
    return "\n".join(lines) + "\n"
