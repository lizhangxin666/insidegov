.PHONY: install api demo demo-stack test lint web-dev web-build web-check verify

install:
	python3 -m pip install -e '.[dev]'

api:
	uv run uvicorn insidegov.api:app --reload --port 8000

demo:
	uv run insidegov demo --seed 42 --fiscal-multiplier 0.5

demo-stack:
	./scripts/start-demo.sh

test:
	uv run pytest -q

lint:
	uv run ruff check src tests

web-dev:
	cd apps/web && npm run dev

web-build:
	cd apps/web && npm run build

web-check:
	cd apps/web && npm run lint && npm run typecheck && npm test && npm run build

verify: lint test web-check
