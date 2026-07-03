.PHONY: install test demo record pre-flight clean

PYTHON ?= python3
UV ?= uv

install:
	$(UV) sync --all-extras 2>/dev/null || $(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest tests/ -v

demo:
	GRADIO_ANALYTICS_ENABLED=False $(PYTHON) -m src.app --demo-mode fixture

demo-live:
	GRADIO_ANALYTICS_ENABLED=False $(PYTHON) -m src.app --demo-mode live

record:
	$(PYTHON) scripts/refresh_cache.py
	$(PYTHON) scripts/validate_replay.py
	$(MAKE) demo

pre-flight: install test
	$(PYTHON) scripts/pre_flight.py

clean:
	rm -rf .pytest_cache __pycache__ src/__pycache__ tests/__pycache__
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
