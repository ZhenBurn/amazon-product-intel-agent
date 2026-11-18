# Amazon 商品情报 Agent

> 把脏、会变、会被封的外部网页，变成可核对、可回写 Excel 的商品情报；确定性系统负责数字，LLM 只负责解释。

项目：读取 `电商分析.xlsx` 的 4 个 ASIN，低频采集 Amazon 公开商品页，抽取价格、销量、星级、评价、图片、五点描述，SQLite 沉淀历史，生成周报并回写 Excel。

**面试导读**：[`docs/interview/README.md`](docs/interview/README.md) · **真实运行证据**：[`docs/evidence/amazon-live-2026-11-18.md`](docs/evidence/amazon-live-2026-11-18.md) · **真实页评估**：[`eval/real_report.md`](eval/real_report.md) · **LLM 评估**：[`eval/llm_report.md`](eval/llm_report.md)

## 面试 / 评审 5 分钟路径

| 时间 | 看什么 | 重点 |
| --- | --- | --- |
| 0:00–0:45 | 本 README | 问题、4 ASIN、真实页面、边界 |
| 0:45–1:45 | [`周报截图`](docs/assets/product-intel-report.png) / [`HTML`](docs/assets/product-intel-report.html) | 运行统计、本周信号、卖家、缺口 |
| 1:45–2:30 | [`Excel 回写`](docs/assets/product-intel-excel.png) / [`历史`](docs/assets/product-intel-excel-history.png) | 15 行历史 + 新行；同日重跑更新 |
| 2:30–3:30 | [`eval/real_report.md`](eval/real_report.md) | 4 个真实页面 × 11 字段，44/44 |
| 3:30–4:15 | [`eval/llm_report.md`](eval/llm_report.md) | JSON 契约、数字 grounding、降级 |
| 4:15–5:00 | [`docs/interview/architecture.md`](docs/interview/architecture.md) | 架构、取舍、边界 |

## 目标商品

| 商品 | ASIN | 类型 | 工作簿 Sheet |
| --- | --- | --- | --- |
| Razer Basilisk V3 | `B09C13PZX7` | 鼠标 | 雷蛇鼠标 |
| ASUS ROG Strix G16 (2025) | `B0DZZWMB2L` | 笔记本 | 华硕ROG电脑 |
| MSI Katana 15 HX | `B0DZFVBQLK` | 笔记本 | 微星笔记本 |
| Samsung T7 Portable SSD 2TB | `B0874XWW23` | 存储 | Samsung T7 |

工作簿里有 15 行历史记录，去重后是 7 个 `(ASIN, 日期)` 快照，覆盖 2025-12-24 至 2026-01-03。`import-excel` 会把它们导入 SQLite。

## 当前状态

| 模块 | 状态 |
| --- | --- |
| Excel 清单读取 + ASIN 解析 | 完成 |
| 历史记录导入（7 个快照） | 完成 |
| 离线 demo（真实快照 JSON，无网络可跑） | 完成 |
| Amazon 采集：curl_cffi + Playwright 兜底 | 完成 |
| 原始 HTML 缓存 / replay / 手动 capture | 完成 |
| CAPTCHA / 404 检测与失败隔离 | 完成 |
| 选择器 + JSON-LD 兜底 | 完成 |
| 图片 URL 升级与去重 | 完成 |
| SQLite v2 + Upsert + run log | 完成 |
| 业务信号（价格/卖家/评价/库存/销量） | 完成 |
| LLM 数字 grounding + 降级 | 完成 |
| 数据质量 stats | 完成 |
| 周报（Markdown/HTML） | 完成 |
| Excel 回写（追加/同日更新/备份） | 完成 |
| 45 个测试 + 三类评估 | 完成 |

## 快速开始

```bash
uv sync --extra dev

# 离线 demo：不访问 Amazon，60 秒出报告 + Excel 副本
uv run python -m app.cli demo --no-open
```

`demo` 会：

1. 优先使用 `data/raw` 缓存 replay；
2. 没有缓存时读 `data/demo/snapshots.json`（真实解析快照，原始 HTML 不提交）；
3. 生成 `reports/latest.md` / `reports/latest.html`；
4. 写出 `data/exports/amazon_products.xlsx` 副本。

真实采集（首次可先导入工作簿历史，demo 也会自动写入历史）：

```bash
uv run python -m app.cli import-excel
uv run python -m app.cli collect --source live --no-open
```

常用命令：

```bash
# 只采一个 ASIN；默认同日复用缓存，--refresh 强制重新访问
uv run python -m app.cli collect --source live --asin B09C13PZX7 --refresh --no-open

# 用已缓存 HTML 回放
uv run python -m app.cli replay --date 2026-11-18

# 浏览器另存页面后导入
uv run python -m app.cli capture --asin B09C13PZX7 --date 2026-11-19 --file page.html

# 重新解析缓存并检查选择器
uv run python -m app.cli verify

# 数据质量与运行统计
uv run python -m app.cli stats
```

## 采集与地区限制

- `curl_cffi` 使用 Chrome TLS 指纹、真实请求头和 `i18n-prefs=USD` / `lc-main=en_US`；失败时切 Playwright（需 `uv sync --extra browser && playwright install chromium`）。
- 默认单线程、请求间隔 6 秒、最多 4 个商品/轮，不做验证码绕过。
- **价格和销量受出口 IP 影响**：如果 Amazon 把配送地址识别为中国，部分商品会隐藏 buybox 价格或只显示 “See All Buying Options”。需要稳定美国价格时配置美国住宅代理：

```bash
AMAZON_PROXY=http://user:pass@us-proxy-host:port
```

- 当前演示环境没有美国代理：Razer/ASUS/MSI 价格缺失，Samsung T7 是第三方卖家价格。报告把 `价格` 写入 `data_gaps`，并记录 seller，不编数字。
- 页面被识别为 CAPTCHA / bot block 时，本轮记为 `blocked` 并保存 `.blocked.html.gz` 证据，不重试、不绕过。
- 原始 HTML 体积大且包含 Amazon 版权内容，`data/raw/` 已加入 `.gitignore`；仓库只保留解析结果、报告和截图。
- Amazon Conditions of Use 限制未经许可的机器人抓取。本项目仅用于小样本、低频、公开页面的技术演示；生产使用请走官方 API 或获得授权。

## 字段口径

| Excel 列 | 来源 | 说明 |
| --- | --- | --- |
| 名称 | `#productTitle` | 缺失时回退 JSON-LD / og:title |
| 产品简介 | `#feature-bullets` | 五点描述，过滤 “Make sure this fits” |
| 产品描述 | `#productDescription` | 回退 `#aplus` / JSON-LD |
| 主图链接 | `#landingImage` | `data-old-hires` / `data-a-dynamic-image` |
| 详情图链接 | `#altImages` | 缩略图升级到 `_AC_SL1500_`，按图片 ID 去重 |
| 价格 | core price / buybox | 排除 List Price、Coupon、分期价 |
| 预计销量 | social proofing | `10K+ bought in past month` 原文 + 桶值 10000 |
| 星级 | `#acrPopover[title]` | 回退 `.a-icon-alt` / JSON-LD |
| 评价数量 | `#acrCustomerReviewText` | 回退 `#acrCustomerReviewLink` / JSON-LD |
| 获取日期 | 采集当天 | 与工作簿 J 列 `yyyy/mm/dd` 格式一致 |

缺失字段不阻断整行：写入空值并在 `data_gaps` 记录；只有 CAPTCHA/404/无缓存才不写 Excel 行。

## Excel 回写

- 读取：`监控商品` 的 A 列名称、B 列 URL，正则提取 10 位 ASIN。
- 默认读 `data/source/amazon_products.xlsx`（已脱敏的演示模板）；要直接用你的 `电商分析.xlsx`，传 `--excel "路径/电商分析.xlsx"` 或设置 `EXCEL_PATH`。
- 写入：对应商品 Sheet 追加一行；`商品数据` 刷新每个商品最新一行。
- 同一天重跑：按 `获取日期` 找到最后一行并更新，不重复追加。
- 默认写副本 `data/exports/amazon_products.xlsx`；`--in-place` 才会改源文件，且自动备份 `*.backup-YYYYmmdd-HHMMSS.xlsx`。
- 长文本按 Excel 单元格上限 32767 截断，并清理非法控制字符。

## 管线

```mermaid
flowchart LR
    A["Excel 监控清单"] --> B["AmazonSource"]
    B -->|live| C["curl_cffi / Playwright"]
    B -->|replay| D["raw HTML cache"]
    B -->|demo| E["data/demo/snapshots.json"]
    C --> D
    D --> F["Parser + JSON-LD"]
    E --> G["Snapshot seed"]
    F --> H["Normalize + gaps"]
    G --> H
    H --> I["SQLite Upsert"]
    I --> J["Signals"]
    I --> K["LLM + grounding"]
    J --> L["Report"]
    K --> L
    H --> M["Excel write-back"]
```

## SQLite

- `products`：ASIN、名称、类目、URL、marketplace、Excel Sheet；
- `snapshots`：价格、List Price、星级、评价、销量、五点、描述、图片、库存、卖家、selector hits；
- `analyses`：结构化分析；
- `run_logs`：成功/跳过/失败/被拦截/缓存命中、耗时和明细。

`(product_id, snapshot_date)` 唯一；同一天重跑 Upsert，不产生重复行。旧版数据库会通过 `ALTER TABLE` 自动补列。

## LLM 分析与数字 grounding

默认 `LLM_MODE=mock`，不依赖 API。mock 分析根据历史快照计算价格/销量趋势、关键变化、建议和置信度。

真实模式：

```bash
LLM_MODE=real
LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
LLM_API_KEY=your_key
LLM_MODEL=your_model
```

所有 LLM 输出必须满足 `ProductAnalysis` JSON 契约。`app/llm_guard.py` 会检查 summary/trend/key_changes/actions 中的数字：

- 允许当前/历史快照、计算出的 delta/百分比、标题/描述中的数字；
- 不在允许集合中的数字 → 判定 grounding 失败；
- 失败 → 降级为确定性分析，`confidence=low`，并写入 `未溯源数字`。

运行真实模型评估：

```bash
uv run python -m eval.run_llm_eval --mode real
```

真实模型评估：8 条 case，grounding 8/8，1 条降级（`key_changes:51` 无来源数字），平均延迟 31.8s，21,601 tokens；详见 `eval/llm_report.md`。

## 报告与信号

`reports/latest.html` 包含：

- 运行统计：总数 / 成功 / 跳过 / 失败 / 被拦截 / 缓存命中 / 耗时；
- 本周信号：第三方卖家、价格变化、评价增长、库存变化、数据缺口；
- 每个商品：ASIN、URL、采集来源、价格、List Price、星级、评价、销量、库存、卖家、主图、详情图数量；
- 五点描述、产品描述摘要、趋势、关键变化、建议、置信度、数据缺口；
- 失败隔离说明。

## 数据质量 stats

```bash
uv run python -m app.cli stats
```

输出字段缺失率、CAPTCHA/失败、缓存命中率、p50/p95 耗时和 selector 命中次数。

## 测试与评估

```bash
uv run pytest -q          # 45 passed
uv run ruff check .       # All checks passed
uv run python -m eval.run_eval          # fixture 评估
uv run python -m eval.run_real_eval     # 真实页面评估（需 data/raw）
uv run python -m eval.run_llm_eval --mode mock
```

当前结果：

- Parser fixture：3 商品 × 2 日期，快照 6/6，字段 42/42，重复行 0；
- 真实页面：[`eval/real_report.md`](eval/real_report.md)，4 ASIN × 11 字段，44/44，HTML hash 固定版本；
- Excel：首次追加 3、同日更新 3、重复追加 0；
- CAPTCHA 检出 PASS；报告卡片 3/3；
- LLM：8 条 case，真实模型 grounding 8/8，1 条降级；`eval/llm_report.md` 记录 mode/model/延迟/token。

## 设计取舍

- **curl_cffi 优先**：比 Playwright 轻，Chrome TLS 指纹能通过多数静态页面；失败再切真实浏览器。
- **replay 默认**：CI 和演示不依赖网络；真实采集结果可复现。
- **HTML 缓存**：保留原始证据和 selector hit，方便页面改版后重跑解析。
- **确定性抽数**：价格、销量、图片由选择器和 JSON-LD 负责；LLM 只做趋势解释。
- **缺口显式化**：价格、销量、图片缺失都写进 `data_gaps`，不编造。
- **Excel 是交付物**：采集结果直接进入用户已有的分析工作簿，而不是只产出一个孤立 CSV。
- **小样本刻意选择**：4 个 ASIN 足够覆盖成功、缺价格、第三方卖家、CAPTCHA/404、Excel 更新和 LLM 降级。

## 边界

- 小样本、低频、单机；不是生产级爬虫。
- 不绕过 CAPTCHA，不登录，不加购物车，不采集个人信息。
- 不保证所有地区/账号看到同一价格；美国 IP/代理是 buybox 价格的前提。
- 页面改版会导致选择器失效；`verify` 和缓存 HTML 用于快速定位。
- 报告是情报辅助，不构成采购或投资建议。

## 目录

```text
app/
├─ config.py
├─ models.py
├─ errors.py
├─ excel_io.py
├─ demo_data.py
├─ demo_runner.py
├─ images.py
├─ parse.py
├─ normalize.py
├─ signals.py
├─ stats.py
├─ store.py
├─ llm.py
├─ llm_guard.py
├─ report.py
├─ pipeline.py
├─ cli.py
├─ sources/amazon.py
├─ templates/report.html.j2
data/
├─ source/amazon_products.xlsx   # 脱敏演示模板
├─ demo/snapshots.json           # 真实解析快照，离线 demo
├─ raw/                          # 本地 HTML 缓存（gitignored）
├─ exports/                      # 回写副本（gitignored）
└─ runtime/                      # SQLite（gitignored）
docs/
├─ assets/              # 周报 / Excel 截图
├─ evidence/
└─ interview/
eval/
├─ real_pages/expected.json
├─ run_eval.py
├─ run_real_eval.py
├─ run_llm_eval.py
├─ real_report.md
├─ llm_report.md
└─ report.md
scripts/
└─ export_demo_snapshot.py
tests/
```

## License

MIT
