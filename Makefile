# 启动记账应用:make run(直接 `make` 等效)
.PHONY: run sync

run:
	uv run streamlit run src/nq_finance/app.py
sync:
	uv sync
format:
	uv run ruff format .
check:
	uv run ruff check --fix .
