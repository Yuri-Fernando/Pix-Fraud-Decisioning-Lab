PYTHON ?= python
export PYTHONPATH := src

.PHONY: test run sweep med-demo

test:
	$(PYTHON) -m pytest

run:
	$(PYTHON) -m pixfraud run --out reports

sweep:
	$(PYTHON) -m pixfraud sweep

med-demo:
	$(PYTHON) -m pixfraud med-demo
