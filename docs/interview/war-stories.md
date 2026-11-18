# 真实 bug 与修复

## 1. Excel 图片 URL 被逗号切断

**现象**：Samsung T7 的详情图 URL 在重新导入 Excel 后变成 `..._AC_SR38` 和 `50_.jpg` 两段。

**根因**：Amazon 图片 URL 本身含逗号（`_AC_SR38,50_`），旧逻辑按逗号切分多图单元格。

**修复**：只按换行或“逗号后紧跟 `https://`”切分；写回时用换行分隔。

**回归**：`tests/test_excel.py` 断言 Samsung 保留 7 张图和 `_AC_SR38,50_`。

## 2. 获取日期显示成 `2026-11-18 00:00:00`

**现象**：Excel 截图中日期带时间，或 `商品数据` Sheet 显示序列号 `46344`。

**根因**：`_write_row` 对所有值调用 `str()`，把 `datetime` 变成了字符串；汇总 Sheet 的模板单元格是 General，日期格式没有继承。

**修复**：`_truncate` 保留 `datetime/date` 类型；写回时强制日期格式 `yyyy/mm/dd`。

**回归**：`tests/test_excel.py`、`tests/test_pipeline.py` 检查日期和行内容。

## 3. 中国出口 IP 下价格缺失

**现象**：Razer/ASUS/MSI 页面没有 buybox 价格；ASUS/MSI 还提示 “cannot be shipped”。

**根因**：Amazon 根据配送地址/地区隐藏价格或销量，不是解析器 bug。

**处理**：不编价格，写入 `data_gaps`；报告和 Excel 保留空值；Samsung 的第三方价格记录 seller，并提示不可与历史 buybox 直接比较。

**证据**：`docs/evidence/amazon-live-2026-11-18.md`、`eval/real_report.md`。

## 4. replay 不能悄悄用别的日期

**现象**：请求 `2026-11-19` 时，如果只有 `2026-11-18` 缓存，旧逻辑会回退到最新缓存，导致快照日期和页面日期不一致。

**根因**：为了“有数据”牺牲了日期语义。

**修复**：replay 只读精确日期；没有就 `CacheMissError`，报告标记 skipped。`demo` 自己选择最新缓存日期或离线快照。

**回归**：`tests/test_pipeline.py::test_pipeline_failure_isolation` 覆盖无缓存/拦截隔离。

## 5. 报告里出现 `None`

**现象**：ASUS/MSI 的预计销量单元格显示 `None`，不是 `—`。

**根因**：模板直接输出 `snapshot.sales_text`，空值时 Jinja 渲染成字符串 `None`。

**修复**：`sales_display = snapshot.sales_text or "—"`，并增加 seller/stock 显示。

**回归**：报告截图检查、离线 demo 测试。
