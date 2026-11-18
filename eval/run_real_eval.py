"""Evaluate the parser against hand-labelled real Amazon pages.

Raw HTML stays under data/raw and is not committed. The committed artifacts are
the expected labels, hashes, results, and this report.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from app.excel_io import load_watchlist
from app.normalize import build_snapshot
from app.parse import parse_product_page

EVAL_DIR = Path(__file__).resolve().parent
PROJECT_DIR = EVAL_DIR.parent
EXPECTED_PATH = EVAL_DIR / "real_pages" / "expected.json"
RESULTS_PATH = EVAL_DIR / "real_results.json"
REPORT_PATH = EVAL_DIR / "real_report.md"
DEFAULT_HTML_DIR = PROJECT_DIR / "data" / "raw"
DEFAULT_EXCEL = PROJECT_DIR / "data" / "source" / "amazon_products.xlsx"

FIELDS = [
    "title_contains",
    "price",
    "list_price",
    "rating",
    "reviews",
    "sales_text",
    "bullets_count",
    "main_image",
    "gallery_count",
    "seller_present",
    "availability_contains",
]


def _actual(snapshot: Any) -> dict[str, Any]:
    return {
        "title_contains": snapshot.title,
        "price": snapshot.price,
        "list_price": snapshot.list_price,
        "rating": snapshot.rating,
        "reviews": snapshot.reviews,
        "sales_text": snapshot.sales_text,
        "bullets_count": len(snapshot.bullets),
        "main_image": bool(snapshot.main_image),
        "gallery_count": len(snapshot.gallery_images),
        "seller_present": bool(snapshot.seller),
        "availability_contains": snapshot.availability,
    }


def _compare(field: str, actual: Any, expected: Any) -> bool:
    if field == "title_contains":
        return bool(actual) and str(expected).lower() in str(actual).lower()
    if field == "availability_contains":
        if expected is None:
            return True
        return bool(actual) and str(expected).lower() in str(actual).lower()
    if field in {"price", "list_price", "rating"}:
        if actual is None or expected is None:
            return actual is None and expected is None
        return math.isclose(
            float(actual),
            float(expected),
            rel_tol=1e-9,
            abs_tol=0.001,
        )
    if field == "reviews":
        return actual == expected
    if field == "sales_text":
        return actual == expected
    if field in {"main_image", "seller_present"}:
        return bool(actual) == bool(expected)
    return actual == expected


def _render_value(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate parser on real Amazon pages")
    parser.add_argument("--html-dir", default=str(DEFAULT_HTML_DIR))
    parser.add_argument("--excel", default=str(DEFAULT_EXCEL))
    args = parser.parse_args(argv)

    payload = json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))
    products = {product.product_id: product for product in load_watchlist(Path(args.excel))}
    html_dir = Path(args.html_dir)

    pages: list[dict[str, Any]] = []
    field_pass = 0
    field_total = 0

    for page in payload["pages"]:
        asin = page["asin"]
        snapshot_date = page["snapshot_date"]
        expected = page["expected"]
        path = html_dir / asin / f"{snapshot_date}.html.gz"
        result: dict[str, Any] = {
            "asin": asin,
            "snapshot_date": snapshot_date,
            "html_path": str(path),
            "notes": page.get("notes", ""),
            "checks": {},
        }

        if not path.exists():
            result["status"] = "skipped"
            result["reason"] = "no cached HTML"
            pages.append(result)
            continue

        html = gzip.open(path, "rt", encoding="utf-8", errors="replace").read()
        actual_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
        result["html_sha256"] = actual_hash
        if actual_hash != page["html_sha256"]:
            result["status"] = "skipped"
            result["reason"] = "cache hash changed; recapture and relabel"
            pages.append(result)
            continue

        product = products.get(asin)
        if product is None:
            result["status"] = "skipped"
            result["reason"] = "ASIN not in watchlist"
            pages.append(result)
            continue

        parsed = parse_product_page(html)
        snapshot = build_snapshot(product, snapshot_date, parsed)
        actual = _actual(snapshot)
        checks: dict[str, bool] = {}
        for field in FIELDS:
            ok = _compare(field, actual.get(field), expected.get(field))
            checks[field] = ok
            field_total += 1
            if ok:
                field_pass += 1
        result["status"] = "checked"
        result["actual"] = {
            key: value if key not in {"title_contains"} else parsed.title
            for key, value in actual.items()
        }
        result["expected"] = expected
        result["checks"] = checks
        result["selector_hits"] = parsed.selector_hits
        pages.append(result)

    checked = [page for page in pages if page["status"] == "checked"]
    skipped = [page for page in pages if page["status"] == "skipped"]
    mismatches = [
        f"{page['asin']}.{field}"
        for page in checked
        for field, ok in page["checks"].items()
        if not ok
    ]
    summary = {
        "captured_at": payload.get("captured_at"),
        "pages_expected": len(payload["pages"]),
        "pages_checked": len(checked),
        "pages_skipped": len(skipped),
        "fields_pass": field_pass,
        "fields_total": field_total,
        "accuracy": round(field_pass / field_total, 4) if field_total else 0,
        "mismatches": mismatches,
        "skipped_reasons": {
            page["asin"]: page.get("reason", "") for page in skipped
        },
    }

    RESULTS_PATH.write_text(
        json.dumps({"summary": summary, "pages": pages}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# 真实 Amazon 页面评估",
        "",
        (
            f"> 采集日期：{summary['captured_at']}；"
            f"检查页面 {summary['pages_checked']}/{summary['pages_expected']}；"
            "人工标注 + 缓存 HTML 文本 SHA256 固定版本。"
        ),
        "",
        "## 结论",
        "",
        (
            f"字段通过 **{summary['fields_pass']}/{summary['fields_total']}**，"
            f"准确率 **{summary['accuracy']:.1%}**；"
            f"跳过 **{summary['pages_skipped']}** 个页面。"
        ),
        "",
        "原始 HTML 不提交到仓库；标签、hash、结果和报告提交。"
        "如果缓存 hash 变化，评估会跳过而不是给出误导结果。",
        "",
        "## 页面结果",
        "",
        "| ASIN | 状态 | 字段通过 | 价格 | 星级 | 评价 | 销量 | 详情图 | 备注 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for page in pages:
        if page["status"] != "checked":
            lines.append(
                f"| {page['asin']} | 跳过 | — | — | — | — | — | — | "
                f"{page.get('reason', '')} |"
            )
            continue
        checks = page["checks"]
        passed = sum(1 for ok in checks.values() if ok)
        actual = page["actual"]
        lines.append(
            f"| {page['asin']} | 已检查 | {passed}/{len(FIELDS)} | "
            f"{_render_value(actual['price'])} | {_render_value(actual['rating'])} | "
            f"{_render_value(actual['reviews'])} | {_render_value(actual['sales_text'])} | "
            f"{actual['gallery_count']} | {page['notes']} |"
        )

    lines.extend(
        [
            "",
            "## 差异",
            "",
        ]
    )
    if mismatches:
        lines.extend(f"- `{item}`" for item in mismatches)
    else:
        lines.append("- 无字段差异。")

    lines.extend(
        [
            "",
            "## 数据边界",
            "",
            (
                "- 当前出口 IP 被识别为中国，Razer/ASUS/MSI 的 buybox 价格缺失，"
                "已作为 `data_gaps` 记录。"
            ),
            (
                "- Samsung T7 的价格来自第三方卖家，不能与历史 buybox 直接比较；"
                "报告会记录卖家并提示人工核实。"
            ),
            (
                "- 真实页面会随地区、账号、卖家和时间变化；"
                "本报告只代表 2026-11-18 的固定 HTML 版本。"
            ),
            "",
            "## 复现",
            "",
            "```bash",
            "uv run python -m eval.run_real_eval",
            "```",
            "",
            "需要有本地 `data/raw` 缓存；没有缓存时会跳过，不会生成假结果。",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"real pages {summary['pages_checked']}/{summary['pages_expected']}, "
        f"fields {summary['fields_pass']}/{summary['fields_total']}, "
        f"accuracy={summary['accuracy']}, skipped={summary['pages_skipped']}, "
        f"mismatches={len(mismatches)}"
    )
    print(f"wrote {REPORT_PATH}")
    print(f"wrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
