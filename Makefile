.PHONY: install demo collect replay import verify stats test lint fmt eval real-eval llm-eval llm-eval-real

install:
	uv sync --extra dev

demo:
	uv run python -m app.cli demo --no-open

collect:
	uv run python -m app.cli collect --source live

replay:
	uv run python -m app.cli replay

import:
	uv run python -m app.cli import-excel

verify:
	uv run python -m app.cli verify

stats:
	uv run python -m app.cli stats

test:
	uv run pytest

eval:
	uv run python -m eval.run_eval

real-eval:
	uv run python -m eval.run_real_eval

llm-eval:
	uv run python -m eval.run_llm_eval --mode mock

llm-eval-real:
	uv run python -m eval.run_llm_eval --mode real

lint:
	uv run ruff check .

fmt:
	uv run ruff format .
