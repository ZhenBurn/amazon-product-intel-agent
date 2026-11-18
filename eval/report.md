# Amazon 商品情报 Agent 评估报告

> 评估集：3 个商品 × 2 个日期；离线 replay 固定页面；mock 分析。

## 结论

存储快照 **6/6**，分析 **6** 条，抽取字段准确 **42/42**。
重复行 **0**，幂等 **PASS**，拦截检出 **PASS**，Excel 回写 **PASS**，报告卡片 **3** 张。

## 运行统计

| 日期 | 成功 | 跳过 | 失败 |
| --- | --- | --- | --- |
| 2026-11-17 | 3 | 0 | 0 |
| 2026-11-18 | 3 | 0 | 0 |

## 字段准确率

| 字段 | 通过 | 总数 |
| --- | --- | --- |
| price | 6 | 6 |
| rating | 6 | 6 |
| reviews | 6 | 6 |
| sales_value | 6 | 6 |
| currency | 6 | 6 |
| main_image | 6 | 6 |
| gallery | 6 | 6 |

## 幂等与失败隔离

- 同日重跑：成功 3，跳过 0，失败 0
- 重复行：0（Upsert 生效）
- CAPTCHA 检出：PASS（blocked=1）

## Excel 回写

- 首次追加：['B0874XWW23', 'B09C13PZX7', 'B0DZZWMB2L']
- 同日更新：['B0874XWW23', 'B09C13PZX7', 'B0DZZWMB2L']
- 追加重复：[]
- 结论：PASS

## JSON 契约与降级

- 分析记录：6 条；置信度分布：{'high': 0, 'medium': 3, 'low': 0}
- 非法 JSON 解析测试：PASS
- 降级分析：PASS（confidence=low，data_gaps 记录原因）

## 报告检查

- HTML 卡片数：3/3
- 关键内容：PASS（Amazon 商品情报周报 / 三个商品名）

## 局限

- 离线评估使用压缩的 Amazon 结构 fixture；真实页面会受地区、账号、变体影响。
- 价格和销量是页面展示口径；销量仍按 K+/百+ 区间记录，不恢复精确值。
- live 采集依赖 curl_cffi 和出口 IP；无美国代理时价格可能缺失。
- 评估关注字段、幂等、拦截、Excel 回写和报告；没有做并发与成本评估。

## 复现

```bash
uv run python -m eval.run_eval
```

产物：`eval/report.md`、`eval/results.json`。