"""Evaluate LLM analysis quality on the committed real snapshot.

The default is real mode. It needs LLM_BASE_URL / LLM_API_KEY / LLM_MODEL.
Use --mode mock for a contract/grounding smoke test without network.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from statistics import median
from typing import Any

from app.config import Settings
from app.demo_data import load_demo
from app.llm import PROMPT_VERSION, MockAnalysisClient, OpenAIAnalysisClient
from app.llm_guard import validate_analysis
from app.models import ProductAnalysis, Snapshot

EVAL_DIR = Path(__file__).resolve().parent
PROJECT_DIR = EVAL_DIR.parent
DEMO = PROJECT_DIR / "data" / "demo" / "snapshots.json"
RESULTS_PATH = EVAL_DIR / "llm_results.json"
REPORT_PATH = EVAL_DIR / "llm_report.md"
MANUAL_PATH = EVAL_DIR / "llm_manual_review.md"


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))
    return round(ordered[index], 2)


def _product_payload(product: Any) -> dict[str, str]:
    return {
        "name": product.name,
        "asin": product.product_id,
        "url": product.url,
        "category": product.category,
    }


def _is_fallback(analysis: ProductAnalysis) -> bool:
    return analysis.title == "分析降级" or analysis.summary.startswith("LLM 分析不可用")


def _cases(demo: Any, limit: int = 0) -> list[tuple[str, Any, Snapshot, list[Snapshot]]]:
    products = {product.product_id: product for product in demo.products}
    cases: list[tuple[str, Any, Snapshot, list[Snapshot]]] = []
    for current in demo.current_snapshots():
        product = products[current.product_id]
        full = demo.history(current.product_id, demo.captured_at, limit=5)
        cases.append((f"{current.product_id}:full", product, current, full))
        cases.append((f"{current.product_id}:short", product, current, [current]))
    return cases[:limit] if limit else cases


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate LLM analysis")
    parser.add_argument("--mode", choices=["real", "mock"], default="real")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    settings = Settings(llm_mode=args.mode)
    if args.mode == "real":
        if not settings.llm_api_key or not settings.llm_model:
            print(
                "LLM_API_KEY / LLM_MODEL is empty. Set them in .env or env, "
                "or run with --mode mock."
            )
            return 1
        client = OpenAIAnalysisClient(settings)
    else:
        client = MockAnalysisClient()

    report_path = REPORT_PATH if args.mode == "real" else EVAL_DIR / "llm_mock_report.md"
    results_path = RESULTS_PATH if args.mode == "real" else EVAL_DIR / "llm_mock_results.json"

    demo = load_demo(DEMO)
    cases = _cases(demo, args.limit)
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    grounding_pass = 0
    fallback_count = 0
    total_tokens: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    for case_id, product, current, history in cases:
        if hasattr(client, "last_usage"):
            client.last_usage = None  # type: ignore[attr-defined]
        started = time.perf_counter()
        analysis = client.analyze(_product_payload(product), current, history)
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        latencies.append(latency_ms)

        grounding = validate_analysis(
            analysis,
            current,
            history,
            _product_payload(product),
        )
        if grounding.ok:
            grounding_pass += 1
        fallback = _is_fallback(analysis)
        if fallback:
            fallback_count += 1
        usage = getattr(client, "last_usage", None)
        if isinstance(usage, dict):
            for key in total_tokens:
                total_tokens[key] += int(usage.get(key) or 0)

        rows.append(
            {
                "case": case_id,
                "asin": current.product_id,
                "product": product.name,
                "history_size": len(history),
                "grounding_ok": grounding.ok,
                "grounding_violations": grounding.violations,
                "fallback": fallback,
                "latency_ms": latency_ms,
                "usage": usage,
                "summary": analysis.summary,
                "price_trend": analysis.price_trend,
                "sales_trend": analysis.sales_trend,
                "key_changes": analysis.key_changes,
                "actions": analysis.actions,
                "confidence": analysis.confidence,
                "data_gaps": analysis.data_gaps,
            }
        )

    summary = {
        "mode": args.mode,
        "model": settings.llm_model if args.mode == "real" else "mock",
        "prompt_version": PROMPT_VERSION,
        "cases": len(rows),
        "grounding_pass": grounding_pass,
        "grounding_rate": round(grounding_pass / len(rows), 4) if rows else 0,
        "fallback_count": fallback_count,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        "p50_latency_ms": round(median(latencies), 2) if latencies else 0,
        "p95_latency_ms": _p95(latencies),
        "tokens": total_tokens,
    }
    results_path.write_text(
        json.dumps({"summary": summary, "cases": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    lines = [
        "# LLM 分析评估",
        "",
        (
            f"> 模式：**{args.mode}**；模型：`{summary['model']}`；"
            f"prompt：`{PROMPT_VERSION}`；样本：{summary['cases']} 条。"
        ),
        "",
        "## 结论",
        "",
        (
            f"Grounding 通过 **{summary['grounding_pass']}/{summary['cases']}**；"
            f"降级 **{summary['fallback_count']}** 条；"
            f"平均延迟 **{summary['avg_latency_ms']:.0f} ms**；"
            f"p95 **{summary['p95_latency_ms']:.0f} ms**。"
        ),
        "",
    ]
    if args.mode == "mock":
        lines.extend(
            [
                "> 本次是 mock 模式，只验证 JSON 契约和 grounding 管线；"
                "真实模型请运行 `uv run python -m eval.run_llm_eval --mode real`。",
                "",
            ]
        )
    lines.extend(
        [
            "## Token 用量",
            "",
            f"- prompt：{total_tokens['prompt_tokens']}",
            f"- completion：{total_tokens['completion_tokens']}",
            f"- total：{total_tokens['total_tokens']}",
            "",
            "## 逐条结果",
            "",
            "| Case | Grounding | 降级 | 延迟 ms | 置信度 | 摘要 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        summary_text = str(row["summary"]).replace("|", "/")
        if len(summary_text) > 80:
            summary_text = summary_text[:80] + "…"
        lines.append(
            f"| {row['case']} | {'PASS' if row['grounding_ok'] else 'FAIL'} | "
            f"{'是' if row['fallback'] else '否'} | {row['latency_ms']:.0f} | "
            f"{row['confidence']} | {summary_text} |"
        )
    lines.extend(["", "## 降级", ""])
    fallbacks = [row for row in rows if row["fallback"]]
    if fallbacks:
        for row in fallbacks:
            gaps = "；".join(row["data_gaps"][-4:])
            lines.append(f"- `{row['case']}`：{gaps}")
    else:
        lines.append("- 无")

    lines.extend(
        [
            "",
            "## 人工评分",
            "",
            "见 `eval/llm_manual_review.md`：具体性、可执行性、是否编造事实，各 1–5 分。",
            "",
            "## 说明",
            "",
            "- 数字 grounding 允许当前/历史快照、计算出的 delta/百分比、标题与描述中的数字。",
            "- 出现无来源数字时，客户端会降级为确定性 fallback，并写入 `data_gaps`。",
            "- 没有 API Key 时不会生成“真实模型”结果；mock 结果会明确标注。",
            "",
            "## 复现",
            "",
            "```bash",
            "uv run python -m eval.run_llm_eval --mode mock",
            "uv run python -m eval.run_llm_eval --mode real",
            "```",
        ]
    )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if args.mode == "real" and not MANUAL_PATH.exists():
        manual = [
            "# LLM 人工评分",
            "",
            "每条 1–5 分；Grounding 结果见 `eval/llm_report.md`。",
            "",
            "| Case | 具体性 | 可执行性 | 是否编造事实 | 备注 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            manual.append(f"| {row['case']} |  |  |  |  |")
        MANUAL_PATH.write_text("\n".join(manual) + "\n", encoding="utf-8")

    print(
        f"llm {args.mode}: cases={summary['cases']}, "
        f"grounding={summary['grounding_pass']}/{summary['cases']}, "
        f"fallback={summary['fallback_count']}, "
        f"avg={summary['avg_latency_ms']}ms"
    )
    print(f"wrote {report_path}")
    print(f"wrote {results_path}")
    if args.mode == "real" and MANUAL_PATH.exists():
        print(f"manual review: {MANUAL_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
