# 高频问题与回答

## 1. 为什么不用 Firecrawl / Scrapy / 现成采集 API？

Firecrawl 能省代理和浏览器维护，但会多一层托管缓存/费用，而且精确字段仍要自己解析；Scrapy 适合大规模、多站点，4 个 ASIN 用不上。这里选 `curl_cffi` 优先 + Playwright 兜底，是为了保留“可控的请求路径 + 自己解析”的工程深度。如果预算允许，生产会优先官方 API 或专用采集 API。

## 2. 价格和销量怎么保证正确？

价格只取 core price/buybox，排除 List Price、Coupon、分期价；销量只记录页面给的 `10K+/500+` 区间，不恢复精确值。第三方卖家、地区限制、缺失字段都写 `data_gaps`，不编数字。真实页评估见 `eval/real_report.md`。

## 3. 页面改版怎么办？

- parser 只负责选择器；采集层和存储层不受影响
- 每个字段有多级 fallback（CSS → JSON-LD）
- `verify` 用缓存 HTML 重跑选择器
- `selector_hits` 记录每个字段命中的选择器
- 真实页 eval 用 SHA256 固定页面版本；hash 变化会跳过而不是误报

## 4. 被 CAPTCHA 怎么办？

记录 `blocked`，保存 `.blocked.html.gz` 证据，不重试绕过；其他商品继续。生产环境会降速、换官方/第三方 API，而不是硬碰验证码。

## 5. 为什么用 SQLite，不用 Postgres？

4 个 ASIN、单机、零配置，SQLite 足够；Upsert 解决幂等。面试官如果问 10 万 ASIN，我会切 Postgres/ClickHouse + 队列 + 对象存储，见 `scale-up.md`。

## 6. 为什么输出 Excel，而不是 CSV/数据库？

用户的工作流就在 Excel：`电商分析.xlsx` 已有 15 行历史。项目默认写副本、同日更新、原地写自动备份。Excel 是交付物，数据库是内部状态。

## 7. LLM 会不会编数字？

会，所以不让它产数。`app/llm_guard.py` 校验 summary/trend/key_changes/actions 里的数字，只允许当前/历史快照、计算出的 delta/百分比、标题/描述中的数字；不通过就降级到确定性分析，并记录 `未溯源数字`。真实模型 8 条 case 中 grounding 8/8，1 条因 `key_changes:51` 无来源数字降级。

## 8. 你怎么评估抽取质量？

- 单元：45 个 parser/normalize/store/Excel/LLM guard/signals 测试
- fixture：3 商品 × 2 日期，42/42 字段
- 真实页面：4 个 ASIN × 11 字段，44/44，HTML SHA256 固定版本
- 数据质量：字段缺失率、CAPTCHA、重复行、Excel append/update
- 边界：缺价格/第三方卖家不当作“抽错”，而是记录上下文

## 9. 怎么扩展到 10 万 ASIN？

队列（SQS/Redis）+ worker 池 + 每域名限速 + 代理池 + S3 原始 HTML + Postgres/ClickHouse + Prometheus/Grafana + 告警 + 成本控制 + 官方 API。详见 `scale-up.md`。当前不做，是因为 4 个 ASIN 不需要。

## 10. 最大的 bug 是什么？

Excel 图片 URL 里含 `_AC_SR38,50_`，旧逻辑按逗号切分会把 URL 切断；现在用换行 + 逗号后接 `https://` 的 lookahead 切分。另一个是日期写成字符串导致 Excel 显示 `2026-11-18 00:00:00`，改为保留 datetime + 日期格式。见 `war-stories.md`。

## 11. 如果重做，你会改什么？

- 官方 API 或稳定美国代理，补全价格
- 真实页评估集扩到 30–50 个页面
- 调度与告警（价格阈值、卖家变化）
- 结构化 trace / 成本看板
- 多 marketplace/类目

## 12. 这个项目有什么不做的？

不做大规模爬虫、不绕 CAPTCHA、不登录、不加购物车、不采个人信息、不做多租户权限，也不为了技术栈上 Kafka/K8s。范围小是刻意选择。

## 13. 没有美国代理，价格缺失怎么办？

不补假数据。报告把 `价格` 写入 `data_gaps`；Samsung T7 有第三方价格，记录 seller 并提示不可与历史 buybox 直接比较；Excel 历史里有完整价格，用于展示字段口径。生产用美国代理/官方 API 补全。

## 14. 为什么 4 个 ASIN 也能算作品？

重点不是数量，而是闭环：成功、缺价格、第三方卖家、CAPTCHA/404、Excel 更新、LLM 降级都能在一个小样本里覆盖。扩 ASIN 是工程问题，不是叙事问题。

## 15. 和 NL2SQL 案例是什么关系？

同一个方法论的两面：

- NL2SQL：数字必须来自数据库，模型不能编
- 商品情报：外部数据必须可采集、可校验、可回写、可解释

两者都是“确定性核心 + LLM 边缘 + 评估 + 失败可见”。
