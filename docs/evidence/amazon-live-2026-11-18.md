# Amazon Live Run Evidence · 2026-11-18

> 4 个真实 ASIN、curl_cffi 200、原始 HTML 本地缓存、Excel 回写。原始 HTML 不提交到仓库；本文件记录可核对的 hash、字段和缺口。

## 环境

- Windows 10 / PowerShell 5.1
- Python 3.12.13，curl_cffi 0.17.0
- 未配置美国代理；Amazon 配送地址被识别为 China
- 采集方式：`curl_cffi`，Chrome TLS impersonation
- 页面语言：`en_US`，币种：USD

## 运行命令

```powershell
uv run python -m app.cli collect --source live --asin B09C13PZX7 --refresh --no-excel
uv run python -m app.cli collect --source live --asin B0DZZWMB2L --refresh --no-excel
uv run python -m app.cli collect --source live --asin B0DZFVBQLK --refresh --no-excel
uv run python -m app.cli collect --source live --asin B0874XWW23 --refresh --no-excel
uv run python -m app.cli demo --no-open
```

结果：

```text
2026-11-18: success=4 skipped=0 failed=0 blocked=0 cache_hits=4 source=replay
```

## 缓存与字段

| ASIN | HTTP | 获取时间 (UTC) | gzip bytes | HTML text SHA256 | 价格 | 星级 | 评价 | 销量 | 详情图 | 缺口 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B09C13PZX7 | 200 | 2026-11-18T05:57:48 | 453637 | `8a7bf5d2…3ce172` | — | 4.6 | 10,769 | 5K+ bought in past month | 7 | 价格 |
| B0DZZWMB2L | 200 | 2026-11-18T05:29:44 | 409178 | `d18c4362…3e1a10` | — | 4.4 | 649 | — | 7 | 价格、预计销量 |
| B0DZFVBQLK | 200 | 2026-11-18T05:29:50 | 405514 | `fbf5e084…770b4f` | — | 4.0 | 381 | — | 4 | 价格、预计销量 |
| B0874XWW23 | 200 | 2026-11-18T05:25:21 | 475858 | `a8e2294e…c23101` | $436.99 | 4.7 | 5,132 | 1K+ bought in past month | 7 | 无 |

说明：

- SHA256 是对缓存 HTML 文本（UTF-8）计算的版本标识，用于固定真实页面版本；不是 Amazon 原始响应字节 hash。
- ASUS/MSI 页面提示 “This item cannot be shipped to your selected delivery location”，价格和销量缺失。
- Samsung T7 的价格来自第三方卖家（报告记录 seller），不能直接与历史 buybox 价格比较。
- 价格缺失不会阻断快照写入；`data_gaps` 明确记录。

## 解析选择器

| 字段 | 选择器 / 兜底 | 结果 |
| --- | --- | --- |
| title | `#productTitle` | 4/4 |
| price | core price / buybox / JSON-LD | 1/4（仅 Samsung） |
| list price | `#corePriceDisplay_desktop_feature_div .basisPrice` | 1/4（Samsung） |
| rating | `#acrPopover[title]` | 4/4 |
| reviews | `#acrCustomerReviewText` | 4/4 |
| sales | `#socialProofingAsinFaceout_feature_div` / text regex | 2/4 |
| bullets | `#feature-bullets li span.a-list-item` | 4/4 |
| description | `#productDescription` | 4/4 |
| main image | `#landingImage[data-old-hires]` | 4/4 |
| gallery | `#altImages li img` | 4/4 |
| seller | `#merchantInfoFeature_feature_div` | 1/4（Samsung） |

完整字段对照见 `eval/real_report.md`。

## Excel 回写

- 默认输出：`data/exports/amazon_products.xlsx`（副本）
- 4 个商品 Sheet 各追加 1 行，`获取日期 = 2026/11/18`
- `商品数据` 刷新为 4 行
- 同日重跑：`export-excel` 输出 `appended=0 updated=4 skipped=0`
- 源工作簿 `data/source/amazon_products.xlsx` 未被修改

## 可核对产物

- 报告：`reports/latest.html` / `reports/latest.md`
- 真实页评估：`eval/real_report.md`
- 评估结果：`eval/real_results.json`
- 页面截图：`docs/assets/product-intel-report.png`
- 本地缓存：`data/raw/{ASIN}/2026-11-18.html.gz`（gitignored）
- Excel 副本：`data/exports/amazon_products.xlsx`（gitignored）

## 边界

- 这是 4 个 ASIN 的低频技术演示，不是生产爬虫。
- 未绕过 CAPTCHA，未登录，未加入购物车。
- 价格/销量受地区、账号、卖家和时间影响；报告不构成采购或投资建议。
