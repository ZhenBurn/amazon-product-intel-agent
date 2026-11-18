# 如果扩展到 10 万 ASIN

> 当前是 4 个 ASIN、单机、SQLite。以下是白板方案，不是已实现功能。

## 1. 采集

```text
Excel/DB watchlist
  -> scheduler (APScheduler / Airflow / GitHub Actions 本地 runner)
  -> queue (SQS / Redis Streams)
  -> worker pool (httpx/curl_cffi + Playwright fallback)
  -> per-domain rate limiter
  -> proxy pool (residential / country-specific)
  -> S3 raw HTML + metadata
```

- 每个 ASIN 一个 job，按 marketplace/类目分片
- 每域名 QPS、并发、重试预算独立配置
- CAPTCHA/403 进入 dead-letter + 人工队列，不无限重试
- 原始 HTML 存对象存储，数据库只存路径/哈希/解析结果

## 2. 存储

- Postgres：products、snapshots、analyses、runs、alerts
- ClickHouse：大体积快照/趋势查询
- S3：raw HTML、截图、报告
- Redis：去重、限速、短期缓存
- 分区：按日期/ marketplace / category

## 3. 数据质量

- Pydantic + Great Expectations 风格规则
- 价格 > 0、评分 0–5、评价数不无故下降、销量桶单调
- 每个字段缺失率、selector 命中率、页面结构 hash
- 抽样人工复核 + 多源交叉验证（官方 API / 第三方 API）
- 页面改版告警：某字段缺失率突增 / selector 命中率下降

## 4. 可观测性

- Prometheus/Grafana：成功率、blocked 率、p50/p95、队列深度、代理成本
- OpenTelemetry trace：run → product → fetch → parse → analyze
- 每轮 run JSONL：ASIN、HTTP、缓存、selector hits、缺口、耗时
- 告警：价格阈值、评分下降、卖家变化、连续 blocked

## 5. 成本与合规

- 代理/API 成本按 ASIN 分摊
- LLM 只处理变化明显的商品，控制 token
- 官方 API 优先；第三方 API 作为弹性补充
- 不登录、不绕 CAPTCHA、不采个人信息；保留合规说明

## 6. 分层落地

1. 现在：4 ASIN + SQLite + 单进程
2. 1000 ASIN：Postgres + 队列 + 3–5 worker + 代理池
3. 10 万 ASIN：分片队列 + 对象存储 + ClickHouse + 监控/告警 + 成本看板

**面试重点**：不是背技术栈，而是说清楚每一步为什么现在不做。
