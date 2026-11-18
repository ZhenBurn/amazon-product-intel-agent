# 2 分钟演示

## 0:00–0:20 问题

跨境竞品调研靠手动抄价格、评分、评价、销量到 Excel。漏一次趋势就断，格式不统一历史不可比，页面还会改版、限地区、出 CAPTCHA。

## 0:20–0:40 一条命令跑离线 demo

```powershell
uv run python -m app.cli demo --no-open
```

不访问 Amazon，直接读 `data/demo/snapshots.json`（真实解析快照，原始 HTML 不提交），生成报告和 Excel 副本。

## 0:40–1:10 报告

打开 `reports/latest.html`：

- 4 个 ASIN、成功/跳过/失败、缓存命中
- 本周信号：第三方卖家、价格变化、缺价格
- 每个商品：ASIN、卖家、价格、销量、主图、五点、趋势、缺口

强调：价格缺失不是藏起来，而是 `data_gaps`。

## 1:10–1:35 Excel

打开 `../assets/product-intel-excel.png` 和 `../assets/product-intel-excel-history.png`：

- 15 行历史完整价格
- 2026-11-18 新行
- 同一天重跑 `updated=4`、`appended=0`
- 默认写副本，源工作簿不动

## 1:35–1:55 真实页面与 LLM 边界

- `eval/real_report.md`：4 个真实页面 × 11 字段，44/44，HTML hash 固定版本
- `eval/llm_report.md`：JSON 契约、数字 grounding、失败降级
- `app/llm_guard.py`：无来源数字直接拒绝

## 1:55–2:00 边界

低频、4 个 ASIN、非生产；不绕 CAPTCHA；生产走官方 API/美国代理。下一步：真实 LLM 评估、队列化采集、监控告警。
