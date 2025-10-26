.PHONY: bootstrap test sample-suite lint clean-logs

bootstrap:
	@bash scripts/bootstrap.sh

bootstrap-no-test:
	@RUN_TESTS=0 bash scripts/bootstrap.sh

test:
	@.venv/bin/python -m pytest

.PHONY: perf
perf:
	@.venv/bin/python -m pytest -q tests/test_performance_baseline.py

sample-suite:
	@.venv/bin/python -m elspeth.cli --settings config/sample_suite/settings.yaml --suite-root config/sample_suite --head 0 --live-outputs

.PHONY: sample-suite-artifacts
sample-suite-artifacts:
	@.venv/bin/python -m elspeth.cli \
		--settings config/sample_suite/settings.yaml \
		--suite-root config/sample_suite \
		--reports-dir outputs/sample_suite_reports \
		--artifacts-dir artifacts \
		--signed-bundle \
		--head 0

.PHONY: job
job:
	@JOB?=config/jobs/sample_job.yaml; \
	ARTDIR?=artifacts; \
	.venv/bin/python -m elspeth.cli --job-config $$JOB --head 0 --artifacts-dir $$ARTDIR --signed-bundle

.PHONY: docker-build-dev
docker-build-dev:
	@docker build --target dev -t elspeth:devtest .

.PHONY: test-container
test-container: docker-build-dev
	@docker run --rm elspeth:devtest pytest -m "not slow" --maxfail=1 --disable-warnings

lint:
	@.venv/bin/python -m ruff format docs src tests
	@.venv/bin/python -m ruff check docs src tests
	@.venv/bin/python -m mypy src/elspeth

.PHONY: verify-locked
verify-locked:
	@.venv/bin/python scripts/verify_locked_install.py -r requirements-dev.lock

.PHONY: validate-templates
validate-templates:
	@.venv/bin/python scripts/validate_templates.py

clean-logs:
	@echo "Removing JSONL run logs under ./logs..."
	@rm -f logs/run_*.jsonl || true

sbom:
	@.venv/bin/python -m cyclonedx_py requirements requirements.lock --output-format JSON --output-file sbom.json --output-reproducible

audit:
	@.venv/bin/pip-audit -r requirements.lock --require-hashes

# ============================================================================
# Documentation Targets
# ============================================================================

.PHONY: docs-deps
docs-deps:  ## Install documentation dependencies from hash-pinned lockfile
	@echo "Installing documentation dependencies..."
	@.venv/bin/python -m pip install -r site-docs/requirements-docs.lock --require-hashes
	@echo "Installing Elspeth package in editable mode (no deps)..."
	@.venv/bin/python -m pip install -e . --no-deps

.PHONY: docs-generate
docs-generate:  ## Regenerate auto-generated plugin documentation
	@echo "Generating plugin documentation..."
	@.venv/bin/python scripts/generate_plugin_docs.py

.PHONY: docs-serve
docs-serve:  ## Serve formal documentation locally
	@echo "Starting documentation server at http://127.0.0.1:8000..."
	cd site-docs && ../.venv/bin/mkdocs serve

.PHONY: docs-build
docs-build:  ## Build formal documentation (strict mode)
	@echo "Building documentation with strict mode..."
	cd site-docs && ../.venv/bin/mkdocs build --strict

.PHONY: docs-deploy
docs-deploy:  ## Deploy documentation to GitHub Pages
	@echo "Deploying documentation to GitHub Pages..."
	cd site-docs && ../.venv/bin/mkdocs gh-deploy --force
