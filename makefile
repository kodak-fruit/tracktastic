LINT_TARGETS := *.py

.PHONY: update
update:
	.venv/bin/python3 update.py

.PHONY: update-active
update-active:
	.venv/bin/python3 update.py --active

.PHONY: sync
sync:
	.venv/bin/python3 sync.py

.PHONY: env
env:
	python3 -m venv .venv
	source .venv/bin/activate
	.venv/bin/python3 -m pip install -r requirements.txt -U --quiet

.PHONY: clean
clean:
	rm -rf output/

.PHONY: flake8
flake8:
	.venv/bin/flake8 ${LINT_TARGETS}

.PHONY: pylint
pylint:
	.venv/bin/pylint ${LINT_TARGETS}

.PHONY: mypy
mypy:
	.venv/bin/mypy ${LINT_TARGETS}

.PHONY: isort
isort:
	.venv/bin/isort ${LINT_TARGETS}

.PHONY: isort-check
isort-check:
	.venv/bin/isort --check ${LINT_TARGETS}

.PHONY: black
black:
	.venv/bin/black ${LINT_TARGETS}

.PHONY: black-check
black-check:
	.venv/bin/black --check ${LINT_TARGETS}

.PHONY: format
format: isort black

.PHONY: lint
lint: flake8 pylint mypy isort-check black-check
