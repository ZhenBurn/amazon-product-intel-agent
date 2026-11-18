# Amazon 商品情报 Agent · 面试导读

> 一句话：把脏、会变、会被封的外部网页，变成可核对、可回写 Excel 的商品情报；确定性系统负责数字，LLM 只负责解释。

## 5 分钟作品集路径

| 时间 | 看什么 | 重点 |
| --- | --- | --- |
| 0:00–0:45 | 根目录 `README.md` | 问题、4 个 ASIN、真实页面、边界 |
| 0:45–1:45 | [`周报截图`](../assets/product-intel-report.png) / [`HTML`](../assets/product-intel-report.html) | 运行统计、本周信号、卖家、缺口、五点/图片 |
| 1:45–2:30 | [`Excel 回写`](../assets/product-intel-excel.png) / [`历史`](../assets/product-intel-excel-history.png) | 15 行历史 + 新行；同日重跑只更新 |
| 2:30–3:30 | [`eval/real_report.md`](../../eval/real_report.md) | 4 个真实页面、11 字段、44/44、HTML hash |
| 3:30–4:15 | [`eval/llm_report.md`](../../eval/llm_report.md) | JSON 契约、数字 grounding、降级 |
| 4:15–5:00 | [`architecture.md`](architecture.md) / [`tradeoffs.md`](tradeoffs.md) | 架构、取舍、边界、下一步 |

## 证据地图

| 结论 | 证据 |
| --- | --- |
| 真的采了 Amazon | [`docs/evidence/amazon-live-2026-11-18.md`](../evidence/amazon-live-2026-11-18.md)：HTTP 200、缓存 hash、字段 |
| 真实页面抽对了 | [`eval/real_report.md`](../../eval/real_report.md)：4 ASIN × 11 字段 |
| 同一天重跑幂等 | [`eval/real_results.json`](../../eval/real_results.json)、Excel 截图、`tests/test_excel.py` |
| LLM 不编数字 | [`app/llm_guard.py`](../../app/llm_guard.py)、`tests/test_llm_guard.py`、`eval/llm_report.md` |
| 真实 LLM 模型 | [`eval/llm_report.md`](../../eval/llm_report.md)：8 条 case，grounding 8/8，1 条降级；运行步骤见 [`llm-run.md`](llm-run.md) |
| 没有美国代理也能讲清楚 | 报告中的 `data_gaps`、第三方卖家信号、真实页备注 |
| 不依赖网络也能复现 | `data/demo/snapshots.json` + `uv run python -m app.cli demo --no-open` |

## 30 秒版

> 我做了一个 Amazon 商品情报 pipeline。它读取 Excel 里的 4 个 ASIN，低频采集公开商品页，用确定性选择器抽价格、销量、评价、图片，原始 HTML 缓存可 replay，SQLite 做幂等历史，最后回写 Excel。LLM 只做趋势解释，数字必须能回到快照，不通过就降级。真实页面、失败缺口和 Excel 回写都有证据。


