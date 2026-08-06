.PHONY: sync test unit integration e2e conformance lint format typecheck boundaries propagation schemas validate example surrogate scene viewer docs api clean

sync:
	uv sync --locked --all-packages --group dev

test: surrogate
	uv run --locked pytest

unit:
	uv run --locked pytest packages apps adapters domain-packs

integration:
	uv run --locked pytest -m integration

e2e:
	uv run --locked pytest -m e2e

conformance:
	uv run --locked pytest -m conformance

lint:
	uv lock --check
	uv run --locked ruff check .
	uv run --locked ruff format --check .
	uv run --locked pyright
	uv run --locked python scripts/check-boundaries.py
	uv run --locked python scripts/check-propagation.py
	uv run --locked python scripts/generate-schemas.py --check
	uv run --locked python scripts/validate-repository.py
	uv run --locked python scripts/check-version.py

format:
	uv run --locked ruff format .
	uv run --locked ruff check --fix .

typecheck:
	uv run --locked pyright

boundaries:
	uv run --locked python scripts/check-boundaries.py

propagation:
	uv run --locked python scripts/check-propagation.py

schemas:
	uv run --locked python scripts/generate-schemas.py

validate:
	uv lock --check
	uv run --locked python scripts/check-propagation.py
	uv run --locked python scripts/validate-repository.py
	uv run --locked python scripts/check-version.py

example:
	uv run --locked python examples/simulated-color-mixing/run_campaign.py

surrogate:
	uv run --locked --with-editable ./examples/digital-twin-surrogate/adapter pytest examples/digital-twin-surrogate/tests
	uv run --locked opensdl twin validate examples/digital-twin-surrogate/twin.yaml

# Requires the Blender release recorded in scene/assets/node-inventory.json. A skip is a failure
# here: this target exists to prove the scene still rebuilds to the committed bytes.
scene:
	PYTHONPATH=scripts uv run --locked --with-editable ./examples/digital-twin-surrogate/adapter \
		pytest -p pytest_no_skip examples/digital-twin-surrogate/tests/test_scene_reproducibility.py

viewer:
	npm --prefix examples/digital-twin-surrogate/viewer ci
	npm --prefix examples/digital-twin-surrogate/viewer run lint
	npm --prefix examples/digital-twin-surrogate/viewer run typecheck
	npm --prefix examples/digital-twin-surrogate/viewer test
	npm --prefix examples/digital-twin-surrogate/viewer run build
	git diff --exit-code -- examples/digital-twin-surrogate/viewer/static

docs:
	uv run --locked --all-packages --group dev --group docs mkdocs build --strict

api:
	uv run --locked opensdl serve-api --manifest examples/simulated-color-mixing/opensdl.yaml

clean:
	rm -rf .opensdl site .pytest_cache .ruff_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
