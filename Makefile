# SayCue — dev shortcuts (architektura §6, dzień 1: „make dev działa")
.PHONY: dev lint test bench eval models recordings clean

dev:
	uv venv --python 3.11 .venv
	uv pip install --python .venv/bin/python -e ".[dev]"

lint:
	.venv/bin/ruff check src tests bench eval scripts
	.venv/bin/ruff format --check src tests bench eval scripts

test:
	.venv/bin/python -m pytest -m "not models and not audio_device"

test-models:
	.venv/bin/python -m pytest -m models

bench:
	.venv/bin/python bench/asr_latency.py

eval:
	.venv/bin/python eval/run_eval.py

models:
	.venv/bin/python scripts/download_models.py

recordings:
	.venv/bin/python scripts/generate_eval_recordings.py

clean:
	rm -rf .pytest_cache .ruff_cache eval/results bench/results
