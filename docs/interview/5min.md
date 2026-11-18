# 5 分钟深挖

## 1. 问题与约束（40 秒）

- 用户：跨境选品/竞品运营，Excel 是现有工作台
- 约束：没有官方 API 资质、没有美国代理、Amazon 会限地区/反爬、页面会改版
- 目标：低频、可复核、可回写，而不是“抓全网”

## 2. 架构（60 秒）

```text
Excel watchlist
  -> AmazonSource (live: curl_cffi -> Playwright / replay: cache / demo: JSON)
  -> raw HTML cache (gzip + meta)
  -> parser (CSS selector + JSON-LD fallback)
  -> normalize (price / rating / reviews / sales bucket / images)
  -> data gaps
  -> SQLite upsert (ASIN, date)
  -> deterministic signals
  -> mock or real LLM + numeric grounding
  -> Markdown/HTML report
  -> Excel append/update
```

关键设计：

- 采集层和解析层分离：页面改版只影响 parser
- 原始 HTML 缓存：证据、重放、离线评估
- SQLite：零配置、幂等、历史趋势
- Excel：用户已有交付物，不要求用户换工具
- LLM 在最后：只解释，不产数

## 3. 数据质量（60 秒）

- 缺价格/销量：保留快照，写 `data_gaps`，不猜
- 第三方卖家：记录 seller，报告提示不可与 buybox 直接比较
- CAPTCHA/404：保存 `.blocked.html.gz`，不绕过，单商品失败隔离
- 同一天重跑：SQLite Upsert + Excel 按日期更新最后一行
- 图片 URL：缩略图升级到 `_AC_SL1500_`，按图片 ID 去重

## 4. 评估（60 秒）

- Parser fixture：42/42 字段
- 真实页面：4 个 ASIN × 11 字段 = 44/44，HTML hash 固定版本
- LLM：8 条 case，真实模型 grounding 8/8，1 条降级；平均 31.8s
- 测试：45 个；ruff/CI 全绿
- Excel：append/update/无重复

## 5. 取舍（60 秒）

| 选择 | 原因 | 代价 |
| --- | --- | --- |
| curl_cffi 优先 | 比浏览器轻，Chrome TLS 指纹 | 出口 IP 仍可能被限制 |
| Playwright 兜底 | 动态页面/更强反爬 | 重、慢、需要浏览器 |
| replay 缓存 | 可复现、CI 不依赖网络 | 需要管理缓存版本 |
| SQLite | 零配置、单机 | 不适合多 worker |
| Excel 输出 | 用户已有工作流 | 不是数据库/BI |
| LLM 只解释 | 避免编数，成本可控 | 分析深度受输入限制 |

## 6. 失败与下一步（40 秒）

- 失败：中国 IP 下 3/4 价格缺失；Samsung 第三方价格；CAPTCHA
- 下一步：美国代理/官方 API、真实 LLM 评估、队列化、监控告警、更多类目
- 不做的：大规模爬虫、绕过验证码、Kafka/K8s 过度设计

## 7. 一句话收尾

> 这个项目的价值不是“抓了 4 个页面”，而是把外部脏数据变成可核对、可回写、可解释的交付物，并且诚实地暴露边界。
