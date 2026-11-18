"""Markdown and HTML report rendering."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app import store
from app.models import Product, RunLog
from app.signals import Signal, build_signals, top_signals

TEMPLATE_DIR = Path(__file__).parent / "templates"
STATUS_LABELS = {
    "success": "采集完成",
    "skipped": "已跳过",
    "failed": "失败",
    "unknown": "未知",
}
SOURCE_LABELS = {
    "live": "实时 Amazon",
    "replay": "缓存回放",
    "demo": "离线真实快照",
}


def _number(value: float | None, currency: str | None = None) -> str:
    if value is None:
        return "—"
    prefix = currency or ""
    return f"{prefix}{value:,.2f}"


def _short(text: str | None, limit: int = 600) -> str:
    if not text:
        return "—"
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


def build_context(
    conn: sqlite3.Connection,
    run_log: RunLog,
    products: list[Product] | None = None,
) -> dict[str, Any]:
    products = products or store.list_products(conn)
    snapshots = {
        snapshot.product_id: snapshot
        for snapshot in store.list_snapshots(conn, run_log.snapshot_date)
    }
    analyses = {
        analysis.product_id: analysis
        for analysis in store.list_analyses(conn, run_log.snapshot_date)
    }
    details = {detail["product_id"]: detail for detail in run_log.details}

    cards: list[dict[str, Any]] = []
    all_signals: list[Signal] = []
    for product in products:
        detail = details.get(product.product_id, {})
        snapshot = snapshots.get(product.product_id)
        analysis = analyses.get(product.product_id)
        history = store.get_history(
            conn,
            product.product_id,
            run_log.snapshot_date,
            limit=5,
        )
        product_signals = (
            build_signals(snapshot, history, product.name) if snapshot else []
        )
        all_signals.extend(product_signals)
        status = detail.get("status", "unknown")
        data_gaps = snapshot.data_gaps if snapshot else detail.get("data_gaps", [])
        status_label = STATUS_LABELS.get(status, status)
        if status == "success" and data_gaps:
            status_label = "采集完成（有缺口）"
        cards.append(
            {
                "product_id": product.product_id,
                "name": product.name,
                "category": product.category,
                "url": product.url,
                "status": status,
                "status_label": status_label,
                "error": detail.get("error"),
                "source": detail.get("source"),
                "from_cache": detail.get("from_cache", False),
                "snapshot": snapshot,
                "analysis": analysis,
                "data_gaps": data_gaps,
                "history_count": len(history),
                "price_display": _number(
                    snapshot.price if snapshot else None,
                    snapshot.currency if snapshot else None,
                ),
                "list_price_display": _number(
                    snapshot.list_price if snapshot else None,
                    snapshot.currency if snapshot else None,
                ),
                "rating_display": (
                    f"{snapshot.rating:.2f}" if snapshot and snapshot.rating is not None else "—"
                ),
                "reviews_display": (
                    f"{snapshot.reviews:,}"
                    if snapshot and snapshot.reviews is not None
                    else "—"
                ),
                "sales_display": (
                    snapshot.sales_text if snapshot and snapshot.sales_text else "—"
                ),
                "stock_display": (
                    "有货"
                    if snapshot and snapshot.in_stock is True
                    else "无货"
                    if snapshot and snapshot.in_stock is False
                    else "—"
                ),
                "seller_display": (
                    snapshot.seller if snapshot and snapshot.seller else "—"
                ),
                "bullets": snapshot.bullets[:6] if snapshot else [],
                "description": _short(snapshot.description if snapshot else None),
                "main_image": snapshot.main_image if snapshot else None,
                "gallery_count": len(snapshot.gallery_images) if snapshot else 0,
                "selector_hits": snapshot.selector_hits if snapshot else {},
                "signals": product_signals,
            }
        )

    failures = [card for card in cards if card["status"] == "failed"]
    return {
        "run": run_log,
        "products": cards,
        "failures": failures,
        "signals": top_signals(all_signals, limit=3),
        "generated_at": run_log.started_at,
        "source_label": SOURCE_LABELS.get(run_log.source_mode, "缓存回放"),
    }


def render_markdown(context: dict[str, Any]) -> str:
    run: RunLog = context["run"]
    lines = [
        f"# Amazon 商品情报周报 · {run.snapshot_date}",
        "",
        (
            "> 数据来源：amazon.com 商品详情页 · "
            f"采集方式：{context['source_label']} · 本地 SQLite · 非生产"
        ),
        "",
        "## 运行统计",
        "",
        "| 指标 | 数值 |",
        "| --- | --- |",
        f"| 商品总数 | {run.total} |",
        f"| 成功 | {run.success} |",
        f"| 跳过 | {run.skipped} |",
        f"| 失败 | {run.failed} |",
        f"| 被拦截 | {run.blocked} |",
        f"| 缓存命中 | {run.cache_hits} |",
        f"| 耗时 | {run.duration_ms:.0f} ms |",
        "",
    ]

    if context["signals"]:
        lines.extend(["## 本周信号", ""])
        for signal in context["signals"]:
            lines.append(
                f"- **[{signal.severity_label}]** {signal.text} "
                f"（{signal.evidence}）"
            )
        lines.append("")

    for card in context["products"]:
        lines.append(
            f"## {card['name']}（{card['category']}） · {card['status_label']}"
        )
        lines.append("")
        lines.append(f"- ASIN：`{card['product_id']}`")
        lines.append(f"- URL：{card['url']}")
        if card["source"]:
            lines.append(f"- 采集来源：{card['source']}")
        lines.append("")

        snapshot = card["snapshot"]
        if snapshot is not None:
            lines.extend(
                [
                    "| 字段 | 数值 |",
                    "| --- | --- |",
                    f"| 价格 | {card['price_display']} |",
                    f"| List Price | {card['list_price_display']} |",
                    f"| 星级 | {card['rating_display']} |",
                    f"| 评价数 | {card['reviews_display']} |",
                    f"| 预计销量 | {card['sales_display']} |",
                    f"| 库存 | {card['stock_display']} |",
                    f"| 卖家 | {card['seller_display']} |",
                    f"| 主图 | {card['main_image'] or '—'} |",
                    f"| 详情图 | {card['gallery_count']} 张 |",
                    "",
                ]
            )
            if card["bullets"]:
                lines.append("**产品简介**：")
                lines.extend(f"- {item}" for item in card["bullets"])
                lines.append("")
            if card["description"] != "—":
                lines.extend(["**产品描述**：", card["description"], ""])

        analysis = card["analysis"]
        if analysis is not None:
            lines.extend(
                [
                    f"**摘要**：{analysis.summary}",
                    "",
                    f"**价格**：{analysis.price_trend}",
                    "",
                    f"**销量**：{analysis.sales_trend}",
                    "",
                    "**关键变化**：",
                    *[f"- {item}" for item in analysis.key_changes],
                    "",
                    "**建议**：",
                    *[f"- {item}" for item in analysis.actions],
                    "",
                    f"**置信度**：{analysis.confidence}",
                    "",
                ]
            )

        if card["error"]:
            lines.extend([f"**失败原因**：{card['error']}", ""])

        if card["data_gaps"]:
            lines.extend(
                [
                    "**数据缺口**：" + "、".join(card["data_gaps"]),
                    "",
                ]
            )

    if context["failures"]:
        lines.extend(["## 失败与隔离", ""])
        for card in context["failures"]:
            lines.append(
                f"- **{card['name']}**：{card['error']}。其他商品继续处理，未中断本轮运行。"
            )
        lines.append("")

    lines.extend(
        [
            "## 说明",
            "",
            "本报告来自 Amazon 公开商品详情页的低频采集；价格、销量、评价等字段"
            "以采集时页面为准，可能因地区、账号、卖家和时间而变化。"
            "价格可能来自 buybox 或第三方卖家，跨地区/卖家不可直接比较；"
            "销量是 K+/百+ 区间口径，不恢复精确值。"
            "默认使用 mock 分析，真实模型模式需要自行配置 API。"
            "报告不构成采购或投资建议，也不代表 Amazon 或品牌方立场。",
            "",
        ]
    )
    return "\n".join(lines)


def render_html(context: dict[str, Any]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("report.html.j2")
    return template.render(**context)


def write_reports(
    conn: sqlite3.Connection,
    run_log: RunLog,
    report_dir: Path,
    products: list[Product] | None = None,
) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    context = build_context(conn, run_log, products)
    markdown = render_markdown(context)
    html = "\n".join(line.rstrip() for line in render_html(context).splitlines()) + "\n"

    latest_md = report_dir / "latest.md"
    latest_html = report_dir / "latest.html"
    dated_md = report_dir / f"{run_log.snapshot_date}.md"
    dated_html = report_dir / f"{run_log.snapshot_date}.html"

    latest_md.write_text(markdown, encoding="utf-8")
    latest_html.write_text(html, encoding="utf-8")
    dated_md.write_text(markdown, encoding="utf-8")
    dated_html.write_text(html, encoding="utf-8")
    return latest_md, latest_html
