PYTHON?=python
APP_DIRS?=app
PYTHONPATH?=./
TEST_DIR?= tests
PRETTIER?=npx --yes prettier@3

# Paths
app_dirs := .
tests_dir := tests/
web_dirs := app/web
WEB_GLOBS:="$(web_dirs)/**/*.{css,}"
PRETTIER := ./node_modules/.bin/prettier


.PHONY: setup vendor vendor-py vendor-web run share fmt fmt-py fmt-web lint lint-py lint-web test

vendor-py:
	$(PYTHON) -m pip install -r requirements.txt

vendor-web:
	@if [ -f package-lock.json ]; then \
		npm ci; \
	else \
		npm install; \
	fi

vendor: vendor-py vendor-web

run:
	PYTHONPATH=$(APP_DIRS) $(PYTHON) -m uvicorn app.main:app --reload --port 7860

share:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m app.full_pipeline_new

# Python formatting
fmt-py:
	isort $(app_dirs)
	black $(app_dirs)
	isort $(tests_dir)
	black $(tests_dir)

# JS/CSS formatting
fmt-web:
	@test -x $(PRETTIER) || { echo "Prettier not found. Run 'make vendor' first."; exit 127; }
	$(PRETTIER) --write $(WEB_GLOBS)

fmt: fmt-py fmt-web

# Python linting
lint-py:
	@(isok=true; \
	echo "===== black ====="; \
	black --check $(app_dirs) || isok=false; \
	echo "===== flake8 ====="; \
	flake8 $(app_dirs) || isok=false; \
	echo "===== black ====="; \
	black --check $(tests_dir) || isok=false; \
	echo "===== flake8 ====="; \
	flake8 $(tests_dir) || isok=false; \
	$$isok && echo "\nLINTERS OK" || echo "\nLINTERS FAILED"; \
	$$isok;)

# JS/CSS linting
lint-web:
	@test -x $(PRETTIER) || { echo "Prettier not found. Run 'make vendor' first."; exit 127; }
	$(PRETTIER) --check $(WEB_GLOBS)

lint: lint-py lint-web
	
test:
	pytest $(tests_dir)
