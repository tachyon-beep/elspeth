.PHONY: bootstrap test sample-suite lint clean-logs

bootstrap:
	@bash scripts/bootstrap.sh

bootstrap-no-test:
	@RUN_TESTS=0 bash scripts/bootstrap.sh

test:
	@.venv/bin/python -m pytest

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
	@.venv/bin/cyclonedx-bom -r requirements.lock -F json -o sbom.json \
		--project-name elspeth --project-version 0.1.0

audit:
	@.venv/bin/pip-audit -r requirements.lock --require-hashes
