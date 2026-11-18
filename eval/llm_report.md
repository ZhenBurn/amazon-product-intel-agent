# LLM 分析评估

> 模式：**real**；模型：`deepseek-v4.1-flash-1017`；prompt：`analysis_v2`；样本：8 条。

## 结论

Grounding 通过 **8/8**；降级 **1** 条；平均延迟 **31790 ms**；p95 **47864 ms**。

## Token 用量

- prompt：13047
- completion：8554
- total：21601

## 逐条结果

| Case | Grounding | 降级 | 延迟 ms | 置信度 | 摘要 |
| --- | --- | --- | --- | --- | --- |
| B0874XWW23:full | PASS | 否 | 47665 | low | 对比 2026-01-03 与 2026-11-18 快照，Samsung T7 2TB 价格由 187.99 升至 436.99，销量标识由 5K+ 降至 1… |
| B0874XWW23:short | PASS | 否 | 11745 | low | 当前快照日期为2026-11-18，价格436.99美元，标价479.99美元，评分4.7，评论数5132，近月销量文本为“1K+ bought in past… |
| B09C13PZX7:full | PASS | 否 | 17544 | medium | 当前快照（2026-11-18）显示评分4.6、评论数10769、月销5000（5K+ bought in past month）；价格、币种、库存和卖家字段缺… |
| B09C13PZX7:short | PASS | 否 | 38637 | low | 该商品为雷蛇 Basilisk V3 有线人体工学游戏鼠标，当前快照（2026-11-18）显示评分为 4.6，累计评价数 10,769 条，近一个月销量标注为… |
| B0DZFVBQLK:full | PASS | 否 | 9571 | low | 当前快照缺少价格、销量和库存状态，无法判断价格与销售趋势。可确认评分从4.4降至4.0，评论数从186增至381；配送状态从In Stock变为当前地址无法配送… |
| B0DZFVBQLK:short | PASS | 否 | 47864 | low | 该商品为微星 Katana 15 HX 游戏本，配置 Intel Core i9-14900HX、NVIDIA GeForce RTX 5070、32GB DD… |
| B0DZZWMB2L:full | PASS | 是 | 24980 | low | LLM 分析不可用，保留原始数据供人工复核。 |
| B0DZZWMB2L:short | PASS | 否 | 56315 | low | 当前仅有 2026-11-18 单次快照，且与 history 中唯一记录完全一致，因此无法形成任何价格或销量趋势。商品页显示评分 4.4、评论数 649，配置… |

## 降级

- `B0DZZWMB2L:full`：grounding 拦截未溯源数字 `key_changes:51`，回退确定性分析。

## 人工评分

见 `eval/llm_manual_review.md`：具体性、可执行性、是否编造事实，各 1–5 分。

## 说明

- 数字 grounding 允许当前/历史快照、计算出的 delta/百分比、标题与描述中的数字。
- 出现无来源数字时，客户端会降级为确定性 fallback，并写入 `data_gaps`。
- 没有 API Key 时不会生成“真实模型”结果；mock 结果会明确标注。

## 复现

```bash
uv run python -m eval.run_llm_eval --mode mock
uv run python -m eval.run_llm_eval --mode real
```
