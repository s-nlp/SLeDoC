PYTHON?=python
APP_DIRS?=app
PYTHONPATH?=./
TEST_DIR?= ests

.PHONY: vendor run fmt lint test

vendor:
	$(PYTHON) -m pip install -r requirements.txt

run:
	PYTHONPATH=$(APP_DIRS) $(PYTHON) -m uvicorn app.main:app --reload --port 7860

app_dirs := .
app_dirs_with_tests := . tests/
tests_dir := tests/

fmt:
	isort $(app_dirs)
	black $(app_dirs)
	isort $(tests_dir)
	black $(tests_dir)

lint:
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
	
test:
	pytest $(tests_dir)
