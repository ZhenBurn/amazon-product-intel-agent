"""Evaluate the Amazon replay pipeline on 3 products x 2 dates."""

from __future__ import annotations

import gzip
import json
import math
import tempfile
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from app import store
from app.config import Settings
from app.excel_io import write_snapshots
from app.llm import fallback_analysis, parse_analysis_json
from app.pipeline import run_pipeline
from app.sources.amazon import AmazonSource
from tests.amazon_fixture import PRODUCT_A, PRODUCT_B, PRODUCT_C, captcha_page, render_page

EVAL_DIR = Path(__file__).resolve().parent
PROJECT_DIR = EVAL_DIR.parent
EXCEL = PROJECT_DIR / "data" / "source" / "amazon_products.xlsx"
REPORT_PATH = EVAL_DIR / "report.md"
RESULTS_PATH = EVAL_DIR / "results.json"

DATES = ["2026-11-17", "2026-11-18"]
FIELDS = ["price", "rating", "reviews", "sales_value", "currency", "main_image", "gallery"]

EXPECTED = {
    ("B09C13PZX7", "2026-11-17"): {
        "price": 34.99,
        "rating": 4.6,
        "reviews": 9215,
        "sales_value": 10000,
        "currency": "$",
        "main_image": True,
        "gallery": 3,
    },
    ("B09C13PZX7", "2026-11-18"): {
        "price": 32.99,
        "rating": 4.6,
        "reviews": 9250,
        "sales_value": 10000,
        "currency": "$",
        "main_image": True,
        "gallery": 3,
    },
    ("B0874XWW23", "2026-11-17"): {
        "price": 187.99,
        "rating": 4.7,
        "reviews": 37101,
        "sales_value": 5000,
        "currency": "$",
        "main_image": True,
        "gallery": 3,
    },
    ("B0874XWW23", "2026-11-18"): {
        "price": 186.99,
        "rating": 4.7,
        "reviews": 37150,
        "sales_value": 5000,
        "currency": "$",
        "main_image": True,
        "gallery": 3,
    },
    ("B0DZZWMB2L", "2026-11-17"): {
        "price": 1388.97,
        "rating": 4.4,
        "reviews": 430,
        "sales_value": 500,
        "currency": "$",
        "main_image": True,
        "gallery": 3,
    },
    ("B0DZZWMB2L", "2026-11-18"): {
        "price": 1399.99,
        "rating": 4.4,
        "reviews": 435,
        "sales_value": 500,
        "currency": "$",
        "main_image": True,
        "gallery": 3,
    },
}


def _cache(cache_dir: Path, asin: str, snapshot_date: str, html: str) -> None:
    path = cache_dir / asin / f"{snapshot_date}.html.gz"
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write(html)


def _seed_cache(cache_dir: Path) -> None:
    pages = {
        ("B09C13PZX7", "2026-11-17"): render_page(price="$34.99", reviews="(9,215 ratings)"),
        ("B09C13PZX7", "2026-11-18"): render_page(price="$32.99", reviews="(9,250 ratings)"),
        ("B0874XWW23", "2026-11-17"): render_page(
            title="Samsung T7 Portable SSD",
            price="$187.99",
            rating="4.7 out of 5 stars",
            reviews="(37,101 ratings)",
            sales="5K+ bought in past month",
        ),
        ("B0874XWW23", "2026-11-18"): render_page(
            title="Samsung T7 Portable SSD",
            price="$186.99",
            rating="4.7 out of 5 stars",
            reviews="(37,150 ratings)",
            sales="5K+ bought in past month",
        ),
        ("B0DZZWMB2L", "2026-11-17"): render_page(
            title="ASUS ROG Strix G16",
            price="$1,388.97",
            rating="4.4 out of 5 stars",
            reviews="(430 ratings)",
            sales="500+ bought in past month",
        ),
        ("B0DZZWMB2L", "2026-11-18"): render_page(
            title="ASUS ROG Strix G16",
            price="$1,399.99",
            rating="4.4 out of 5 stars",
            reviews="(435 ratings)",
            sales="500+ bought in past month",
        ),
    }
    for (asin, snapshot_date), html in pages.items():
        _cache(cache_dir, asin, snapshot_date, html)
    _cache(cache_dir, "B0DZFVBQLK", "2026-11-19", captcha_page())


def _compare(snapshot: Any, expected: dict[str, Any]) -> dict[str, bool]:
    actual = {
        "price": snapshot.price,
        "rating": snapshot.rating,
        "reviews": snapshot.reviews,
        "sales_value": snapshot.sales_value,
        "currency": snapshot.currency,
        "main_image": bool(snapshot.main_image),
        "gallery": len(snapshot.gallery_images),
    }
    checks: dict[str, bool] = {}
    for field in FIELDS:
        if field in {"price", "rating"} and actual[field] is not None:
            checks[field] = math.isclose(
                float(actual[field]),
                float(expected[field]),
                rel_tol=1e-9,
                abs_tol=0.001,
            )
        else:
            checks[field] = actual[field] == expected[field]
    return checks


def main() -> None:
    settings = Settings(llm_mode="mock")
    products = [PRODUCT_A, PRODUCT_B, PRODUCT_C]
    with tempfile.TemporaryDirectory(prefix="product-intel-eval-") as temp:
        temp_path = Path(temp)
        cache_dir = temp_path / "raw"
        _seed_cache(cache_dir)
        source = AmazonSource(cache_dir=cache_dir, mode="replay")
        db_path = temp_path / "eval.db"
        report_dir = temp_path / "reports"

        day1 = run_pipeline(
            settings, DATES[0], products=products, source=source,
            db_path=db_path, report_dir=report_dir,
        )
        day2 = run_pipeline(
            settings, DATES[1], products=products, source=source,
            db_path=db_path, report_dir=report_dir,
        )
        rerun = run_pipeline(
            settings, DATES[1], products=products, source=source,
            db_path=db_path, report_dir=report_dir,
        )

        conn = store.connect(db_path)
        snapshots_by_date = {
            date: {snapshot.product_id: snapshot for snapshot in store.list_snapshots(conn, date)}
            for date in DATES
        }
        field_pass = 0
        field_total = 0
        field_by_name = {field: {"pass": 0, "total": 0} for field in FIELDS}
        missing: list[str] = []
        mismatch: list[str] = []
        for (asin, snapshot_date), expected in EXPECTED.items():
            stored = snapshots_by_date[snapshot_date].get(asin)
            if stored is None:
                missing.append(f"{asin}@{snapshot_date}")
                field_total += len(FIELDS)
                for field in FIELDS:
                    field_by_name[field]["total"] += 1
                continue
            checks = _compare(stored, expected)
            for field, ok in checks.items():
                field_total += 1
                field_by_name[field]["total"] += 1
                if ok:
                    field_pass += 1
                    field_by_name[field]["pass"] += 1
                else:
                    mismatch.append(f"{asin}@{snapshot_date}:{field}")

        duplicate_rows = store.find_duplicate_snapshots(conn)
        snapshot_count = store.count_snapshots(conn)
        analysis_count = store.count_analyses(conn)
        analyses = store.list_analyses(conn, DATES[1])
        confidence = {
            "high": sum(1 for analysis in analyses if analysis.confidence == "high"),
            "medium": sum(1 for analysis in analyses if analysis.confidence == "medium"),
            "low": sum(1 for analysis in analyses if analysis.confidence == "low"),
        }
        current = snapshots_by_date[DATES[1]].get(PRODUCT_A.product_id)
        day2_snapshots = store.list_snapshots(conn, DATES[1])
        conn.close()

        msi = PRODUCT_A.model_copy(
            update={
                "product_id": "B0DZFVBQLK",
                "name": "MSI Katana 15 HX",
                "excel_sheet": "微星笔记本",
            }
        )
        blocked_run = run_pipeline(
            settings,
            "2026-11-19",
            products=[msi],
            source=source,
            db_path=db_path,
            report_dir=report_dir,
        )

        excel_out = temp_path / "collected.xlsx"
        excel_first = write_snapshots(EXCEL, day2_snapshots, out_path=excel_out)
        excel_second = write_snapshots(EXCEL, day2_snapshots, out_path=excel_out)

        fallback_ok = False
        parse_ok = False
        if current is not None:
            try:
                parse_analysis_json("not json", current)
            except Exception:
                parse_ok = True
                fallback = fallback_analysis(current, "invalid json")
                fallback_ok = (
                    fallback.confidence == "low"
                    and any("invalid json" in gap for gap in fallback.data_gaps)
                )

        html_text = (report_dir / f"{DATES[1]}.html").read_text(encoding="utf-8")
        soup = BeautifulSoup(html_text, "html.parser")
        report_cards = len(soup.select("article.card"))
        report_ok = all(
            marker in html_text
            for marker in ("Amazon 商品情报周报", "Razer Basilisk V3", "Samsung T7", "ASUS ROG")
        )

        run_stats = {
            "day1": [day1.run_log.success, day1.run_log.skipped, day1.run_log.failed],
            "day2": [day2.run_log.success, day2.run_log.skipped, day2.run_log.failed],
            "rerun": [rerun.run_log.success, rerun.run_log.skipped, rerun.run_log.failed],
        }
        block_checks = {
            "blocked": blocked_run.run_log.blocked >= 1,
            "failed": blocked_run.run_log.failed >= 1,
        }
        excel_checks = {
            "first_appended": len(excel_first.appended) == 3,
            "second_updated": len(excel_second.updated) == 3,
            "no_duplicates": len(excel_second.appended) == 0,
        }
        idempotent = (
            snapshot_count == 6
            and analysis_count == 6
            and len(duplicate_rows) == 0
            and (rerun.run_log.success, rerun.run_log.skipped, rerun.run_log.failed)
            == (3, 0, 0)
        )

        summary = {
            "products": len(products),
            "dates": len(DATES),
            "stored_snapshots": snapshot_count,
            "analyses": analysis_count,
            "extraction_pass": field_pass,
            "extraction_total": field_total,
            "extraction_accuracy": round(field_pass / field_total, 4) if field_total else 0,
            "field_by_name": field_by_name,
            "missing": missing,
            "mismatch": mismatch,
            "duplicate_rows": len(duplicate_rows),
            "run_stats": run_stats,
            "block_checks": block_checks,
            "excel_checks": excel_checks,
            "idempotent": idempotent,
            "confidence": confidence,
            "json_contract": {"parse_ok": parse_ok, "fallback_ok": fallback_ok},
            "report_cards": report_cards,
            "report_ok": report_ok,
        }

        d1s, d1k, d1f = run_stats["day1"]
        d2s, d2k, d2f = run_stats["day2"]
        block_status = "PASS" if all(block_checks.values()) else "FAIL"
        excel_status = "PASS" if all(excel_checks.values()) else "FAIL"
        idempotent_status = "PASS" if idempotent else "FAIL"
        parse_status = "PASS" if parse_ok else "FAIL"
        fallback_status = "PASS" if fallback_ok else "FAIL"
        report_status = "PASS" if report_ok else "FAIL"

        report_lines = [
            "# Amazon 商品情报 Agent 评估报告",
            "",
            (
                f"> 评估集：{summary['products']} 个商品 × {summary['dates']} 个日期；"
                "离线 replay 固定页面；mock 分析。"
            ),
            "",
            "## 结论",
            "",
            (
                f"存储快照 **{summary['stored_snapshots']}/6**，"
                f"分析 **{summary['analyses']}** 条，"
                f"抽取字段准确 **{summary['extraction_pass']}/{summary['extraction_total']}**。"
            ),
            (
                f"重复行 **{summary['duplicate_rows']}**，幂等 **{idempotent_status}**，"
                f"拦截检出 **{block_status}**，Excel 回写 **{excel_status}**，"
                f"报告卡片 **{summary['report_cards']}** 张。"
            ),
            "",
            "## 运行统计",
            "",
            "| 日期 | 成功 | 跳过 | 失败 |",
            "| --- | --- | --- | --- |",
            f"| {DATES[0]} | {d1s} | {d1k} | {d1f} |",
            f"| {DATES[1]} | {d2s} | {d2k} | {d2f} |",
            "",
            "## 字段准确率",
            "",
            "| 字段 | 通过 | 总数 |",
            "| --- | --- | --- |",
            *[
                f"| {field} | {values['pass']} | {values['total']} |"
                for field, values in field_by_name.items()
            ],
            "",
            "## 幂等与失败隔离",
            "",
            (
                f"- 同日重跑：成功 {rerun.run_log.success}，"
                f"跳过 {rerun.run_log.skipped}，失败 {rerun.run_log.failed}"
            ),
            f"- 重复行：{summary['duplicate_rows']}（Upsert 生效）",
            f"- CAPTCHA 检出：{block_status}（blocked={blocked_run.run_log.blocked}）",
            "",
            "## Excel 回写",
            "",
            f"- 首次追加：{excel_first.appended}",
            f"- 同日更新：{excel_second.updated}",
            f"- 追加重复：{excel_second.appended}",
            f"- 结论：{excel_status}",
            "",
            "## JSON 契约与降级",
            "",
            f"- 分析记录：{summary['analyses']} 条；置信度分布：{confidence}",
            f"- 非法 JSON 解析测试：{parse_status}",
            f"- 降级分析：{fallback_status}（confidence=low，data_gaps 记录原因）",
            "",
            "## 报告检查",
            "",
            f"- HTML 卡片数：{report_cards}/3",
            f"- 关键内容：{report_status}（Amazon 商品情报周报 / 三个商品名）",
            "",
            "## 局限",
            "",
            "- 离线评估使用压缩的 Amazon 结构 fixture；真实页面会受地区、账号、变体影响。",
            "- 价格和销量是页面展示口径；销量仍按 K+/百+ 区间记录，不恢复精确值。",
            "- live 采集依赖 curl_cffi 和出口 IP；无美国代理时价格可能缺失。",
            "- 评估关注字段、幂等、拦截、Excel 回写和报告；没有做并发与成本评估。",
            "",
            "## 复现",
            "",
            "```bash",
            "uv run python -m eval.run_eval",
            "```",
            "",
            "产物：`eval/report.md`、`eval/results.json`。",
        ]

        REPORT_PATH.write_text("\n".join(report_lines), encoding="utf-8")
        RESULTS_PATH.write_text(
            json.dumps({"summary": summary}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(
            f"stored {summary['stored_snapshots']}/6, "
            f"fields {summary['extraction_pass']}/{summary['extraction_total']}, "
            f"duplicates {summary['duplicate_rows']}, idempotent={idempotent}, "
            f"block={block_status}, excel={excel_status}, report_cards={report_cards}"
        )
        print(f"wrote {REPORT_PATH}")
        print(f"wrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()
