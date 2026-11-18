# 真实 Amazon 页面评估

> 采集日期：2026-11-18；检查页面 4/4；人工标注 + 缓存 HTML 文本 SHA256 固定版本。

## 结论

字段通过 **44/44**，准确率 **100.0%**；跳过 **0** 个页面。

原始 HTML 不提交到仓库；标签、hash、结果和报告提交。如果缓存 hash 变化，评估会跳过而不是给出误导结果。

## 页面结果

| ASIN | 状态 | 字段通过 | 价格 | 星级 | 评价 | 销量 | 详情图 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B09C13PZX7 | 已检查 | 11/11 | — | 4.6 | 10769 | 5K+ bought in past month | 7 | China delivery location hides buybox price; price gap is recorded. |
| B0DZZWMB2L | 已检查 | 11/11 | — | 4.4 | 649 | — | 7 | Region-restricted item; price and sales badge are absent. |
| B0DZFVBQLK | 已检查 | 11/11 | — | 4.0 | 381 | — | 4 | Region-restricted item; gallery has fewer images than the other pages. |
| B0874XWW23 | 已检查 | 11/11 | 436.99 | 4.7 | 5132 | 1K+ bought in past month | 7 | Price comes from a third-party seller, not necessarily the US buybox; seller is recorded and the report warns against direct comparison. |

## 差异

- 无字段差异。

## 数据边界

- 当前出口 IP 被识别为中国，Razer/ASUS/MSI 的 buybox 价格缺失，已作为 `data_gaps` 记录。
- Samsung T7 的价格来自第三方卖家，不能与历史 buybox 直接比较；报告会记录卖家并提示人工核实。
- 真实页面会随地区、账号、卖家和时间变化；本报告只代表 2026-11-18 的固定 HTML 版本。

## 复现

```bash
uv run python -m eval.run_real_eval
```

需要有本地 `data/raw` 缓存；没有缓存时会跳过，不会生成假结果。
