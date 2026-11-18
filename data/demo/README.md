# Offline demo snapshot

`snapshots.json` 是从一次真实 Amazon 采集结果导出的解析快照，用于作品集离线 demo。

- 采集日期：2026-11-18
- 4 个 ASIN；7 条 Excel 历史快照 + 4 条当天快照
- 只包含解析后的字段；不包含原始 HTML
- 长描述和 bullets 已截断；图片只保留主图 + 前 4 张详情图
- 价格/销量缺口保留，不补假数据
- 生成命令：`uv run python -m scripts.export_demo_snapshot`

原始 HTML 在本地 `data/raw/`（gitignored）。真实页评估和运行证据见：

- `eval/real_report.md`
- `docs/evidence/amazon-live-2026-11-18.md`
