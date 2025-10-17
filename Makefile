.PHONY: bootstrap test sample-suite lint

bootstrap:
	@bash scripts/bootstrap.sh

bootstrap-no-test:
	@RUN_TESTS=0 bash scripts/bootstrap.sh

test:
	@.venv/bin/python -m pytest

sample-suite:
	@.venv/bin/python -m elspeth.cli --settings config/sample_suite/settings.yaml --suite-root config/sample_suite --head 0 --live-outputs

lint:
	@.venv/bin/python -m ruff format docs src tests
	@.venv/bin/python -m ruff check docs src tests
	@.venv/bin/python -m mypy src/elspeth

sbom:
	@.venv/bin/cyclonedx-py requirements requirements.lock --pyproject pyproject.toml --output-file sbom.json --output-format JSON --output-reproducible

audit:
	@.venv/bin/pip-audit -r requirements.lock --require-hashes
