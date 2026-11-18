# 跑真实 LLM 评估

当前 `eval/llm_report.md` 已用真实模型跑过：8 条 case，grounding 8/8，1 条降级，平均 31.8s，21,601 tokens。真实模型评估需要本地 key。

## 1. 配置

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

```ini
LLM_MODE=real
LLM_BASE_URL=https://your-openai-compatible-endpoint/v1
LLM_API_KEY=your_key
LLM_MODEL=your_model
```

> 真实的 `.env` 已被 `.gitignore` 忽略；不要把 key 写进文档、截图或提交记录。

不要提交 `.env`。预算控制在 8–12 次调用。

## 2. 运行

```powershell
uv run python -m eval.run_llm_eval --mode real
```

检查：

- `eval/llm_report.md`：模式为 `real`，模型名、grounding、降级、延迟、token
- `eval/llm_results.json`：逐条输出
- `eval/llm_manual_review.md`：人工填具体性/可执行性/是否编造事实（1–5 分）

## 3. 复核与更新

本轮已把 README 的 `mock` 标签替换为真实模型结果。重新跑真实模型后，检查这些位置是否仍准确：

- `README.md` 的 LLM 评估段落
- `docs/interview/README.md` 的证据地图
- `eval/llm_report.md` 的模式/模型/降级原因

如果真实模型有失败/降级，保留在报告里，不要改名成 PASS。失败本身就是作品集的一部分。

## 4. 面试话术

> 我先用 mock 验证契约和 grounding 管线，再用真实小模型跑 8 条；本轮 grounding 8/8，1 条因为无来源数字降级。真实模型的名字、延迟、token 和失败原因都在 `eval/llm_report.md` 里。
