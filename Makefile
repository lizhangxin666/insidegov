.PHONY: install api demo test lint web-dev web-build

install:
	python3 -m pip install -e '.[dev]'

api:
	uvicorn insidegov.api:app --reload --port 8000

demo:
	PYTHONPATH=src python3 -m insidegov.cli run --quarters 16

test:
	PYTHONPATH=src python3 -m pytest -q

lint:
	ruff check src tests

web-dev:
	cd apps/web && npm run dev

web-build:
	cd apps/web && npm run build

