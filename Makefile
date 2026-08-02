.PHONY: sync test unit integration e2e conformance lint format typecheck boundaries schemas example api clean

sync:
	uv sync --all-packages --group dev

test:
	uv run pytest

unit:
	uv run pytest packages apps adapters domain-packs

integration:
	uv run pytest -m integration

e2e:
	uv run pytest -m e2e

conformance:
	uv run pytest -m conformance

lint:
	uv run ruff check .
	uv run pyright
	uv run python scripts/check-boundaries.py
	uv run python scripts/generate-schemas.py --check

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run pyright

boundaries:
	uv run python scripts/check-boundaries.py

schemas:
	uv run python scripts/generate-schemas.py

example:
	uv run python examples/simulated-color-mixing/run_campaign.py

api:
	uv run opensdl serve-api --manifest examples/simulated-color-mixing/opensdl.yaml

clean:
	rm -rf .opensdl site .pytest_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
