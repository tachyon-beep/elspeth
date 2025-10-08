"""Simplified experiment runner ported from legacy implementation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
import json
import logging
import threading
import time

import pandas as pd

from dmp.core.interfaces import LLMClientProtocol, ResultSink
from dmp.core.processing import prepare_prompt_context
from dmp.core.prompts import PromptEngine, PromptTemplate, PromptRenderingError, PromptValidationError
from dmp.core.llm.middleware import LLMMiddleware, LLMRequest
from dmp.core.experiments.plugins import RowExperimentPlugin, AggregationExperimentPlugin, EarlyStopPlugin
from dmp.core.experiments.plugin_registry import create_early_stop_plugin
from dmp.core.controls import RateLimiter, CostTracker
from dmp.core.security import normalize_security_level, resolve_security_level
from dmp.core.artifact_pipeline import ArtifactPipeline, SinkBinding


logger = logging.getLogger(__name__)


@dataclass
class ExperimentRunner:
    llm_client: LLMClientProtocol
    sinks: List[ResultSink]
    prompt_system: str
    prompt_template: str
    prompt_fields: List[str] | None = None
    criteria: List[Dict[str, str]] | None = None
    row_plugins: List[RowExperimentPlugin] | None = None
    aggregator_plugins: List[AggregationExperimentPlugin] | None = None
    rate_limiter: RateLimiter | None = None
    cost_tracker: CostTracker | None = None
    experiment_name: str | None = None
    retry_config: Dict[str, Any] | None = None
    checkpoint_config: Dict[str, Any] | None = None
    _checkpoint_ids: set[str] | None = None
    prompt_defaults: Dict[str, Any] | None = None
    prompt_engine: PromptEngine | None = None
    _compiled_system_prompt: PromptTemplate | None = None
    _compiled_user_prompt: PromptTemplate | None = None
    _compiled_criteria_prompts: Dict[str, PromptTemplate] | None = None
    llm_middlewares: list[LLMMiddleware] | None = None
    concurrency_config: Dict[str, Any] | None = None
    security_level: str | None = None
    _active_security_level: str | None = None
    early_stop_plugins: List[EarlyStopPlugin] | None = None
    early_stop_config: Dict[str, Any] | None = None

    def run(self, df: pd.DataFrame) -> Dict[str, Any]:
        self._init_early_stop()
        processed_ids: set[str] | None = None
        checkpoint_field = None
        checkpoint_path = None
        if self.checkpoint_config:
            checkpoint_path = Path(self.checkpoint_config.get("path", "checkpoint.jsonl"))
            checkpoint_field = self.checkpoint_config.get("field", "APPID")
            processed_ids = self._load_checkpoint(checkpoint_path)

        row_plugins = self.row_plugins or []
        engine = self.prompt_engine or PromptEngine()
        system_template = engine.compile(
            self.prompt_system or "",
            name=f"{self.experiment_name or 'experiment'}:system",
            defaults=self.prompt_defaults or {},
        )
        user_template = engine.compile(
            self.prompt_template or "",
            name=f"{self.experiment_name or 'experiment'}:user",
            defaults=self.prompt_defaults or {},
        )
        criteria_templates: Dict[str, PromptTemplate] = {}
        if self.criteria:
            for crit in self.criteria:
                template_text = crit.get("template", self.prompt_template or "")
                crit_name = crit.get("name") or template_text
                defaults = dict(self.prompt_defaults or {})
                defaults.update(crit.get("defaults", {}))
                criteria_templates[crit_name] = engine.compile(
                    template_text,
                    name=f"{self.experiment_name or 'experiment'}:criteria:{crit_name}",
                    defaults=defaults,
                )
        self._compiled_system_prompt = system_template
        self._compiled_user_prompt = user_template
        self._compiled_criteria_prompts = criteria_templates

        rows_to_process: List[tuple[int, pd.Series, Dict[str, Any], str | None]] = []
        for idx, (_, row) in enumerate(df.iterrows()):
            context = prepare_prompt_context(row, include_fields=self.prompt_fields)
            row_id = context.get(checkpoint_field) if checkpoint_field else None
            if processed_ids is not None and row_id in processed_ids:
                continue
            if self._early_stop_event and self._early_stop_event.is_set():
                break
            rows_to_process.append((idx, row, context, row_id))

        records_with_index: List[tuple[int, Dict[str, Any]]] = []
        failures: List[Dict[str, Any]] = []

        def handle_success(idx: int, record: Dict[str, Any], row_id: str | None) -> None:
            records_with_index.append((idx, record))
            if checkpoint_path and row_id is not None:
                if processed_ids is not None:
                    processed_ids.add(row_id)
                self._append_checkpoint(checkpoint_path, row_id)
            self._maybe_trigger_early_stop(record, row_index=idx)

        def handle_failure(failure: Dict[str, Any]) -> None:
            failures.append(failure)

        concurrency_cfg = self.concurrency_config or {}
        if rows_to_process and self._should_run_parallel(concurrency_cfg, len(rows_to_process)):
            self._run_parallel(
                rows_to_process,
                engine,
                system_template,
                user_template,
                criteria_templates,
                row_plugins,
                handle_success,
                handle_failure,
                concurrency_cfg,
            )
        else:
            for idx, row, context, row_id in rows_to_process:
                if self._early_stop_event and self._early_stop_event.is_set():
                    break
                record, failure = self._process_single_row(
                    engine,
                    system_template,
                    user_template,
                    criteria_templates,
                    row_plugins,
                    context,
                    row,
                    row_id,
                )
                if record:
                    handle_success(idx, record, row_id)
                if failure:
                    handle_failure(failure)

        records_with_index.sort(key=lambda item: item[0])
        results = [record for _, record in records_with_index]

        payload = {"results": results}
        if failures:
            payload["failures"] = failures
        aggregates = {}
        for plugin in self.aggregator_plugins or []:
            derived = plugin.finalize(results)
            if derived:
                aggregates[plugin.name] = derived
        if aggregates:
            payload["aggregates"] = aggregates

        metadata = {
            "rows": len(results),
            "row_count": len(results),
        }
        retry_summary = {
            "total_requests": len(results) + len(failures),
            "total_retries": 0,
            "exhausted": len(failures),
        }
        retry_present = False
        for record in results:
            info = record.get("retry")
            if info:
                retry_present = True
                attempts = int(info.get("attempts", 1))
                retry_summary["total_retries"] += max(attempts - 1, 0)
        for failure in failures:
            info = failure.get("retry")
            if info:
                retry_present = True
                attempts = int(info.get("attempts", 0))
                retry_summary["total_retries"] += max(attempts - 1, 0)
        if retry_present:
            metadata["retry_summary"] = retry_summary

        if aggregates:
            metadata["aggregates"] = aggregates
        if self.cost_tracker:
            summary = self.cost_tracker.summary()
            if summary:
                payload["cost_summary"] = summary
                metadata["cost_summary"] = summary
        if failures:
            metadata["failures"] = failures

        df_security_level = getattr(df, "attrs", {}).get("security_level") if hasattr(df, "attrs") else None
        self._active_security_level = resolve_security_level(self.security_level, df_security_level)
        metadata["security_level"] = self._active_security_level

        if self._early_stop_reason:
            metadata["early_stop"] = dict(self._early_stop_reason)
            payload["early_stop"] = dict(self._early_stop_reason)

        payload["metadata"] = metadata

        pipeline = ArtifactPipeline(self._build_sink_bindings())
        pipeline.execute(payload, metadata)
        self._active_security_level = None
        return payload

    def _init_early_stop(self) -> None:
        self._early_stop_reason = None
        plugins: List[EarlyStopPlugin] = []

        if self.early_stop_plugins:
            plugins = list(self.early_stop_plugins)
        elif self.early_stop_config:
            definition = {"name": "threshold", "options": dict(self.early_stop_config)}
            plugin = create_early_stop_plugin(definition)
            plugins = [plugin]

        if plugins:
            for plugin in plugins:
                try:
                    plugin.reset()
                except AttributeError:
                    pass
            self._active_early_stop_plugins = plugins
            self._early_stop_event = threading.Event()
            self._early_stop_lock = threading.Lock()
        else:
            self._active_early_stop_plugins = []
            self._early_stop_event = None
            self._early_stop_lock = None

    def _maybe_trigger_early_stop(self, record: Dict[str, Any], *, row_index: int | None = None) -> None:
        event: threading.Event | None = getattr(self, "_early_stop_event", None)
        if not event or event.is_set():
            return
        plugins: List[EarlyStopPlugin] = getattr(self, "_active_early_stop_plugins", []) or []
        if not plugins or getattr(self, "_early_stop_reason", None):
            return

        metadata: Dict[str, Any] | None = None
        if row_index is not None:
            metadata = {"row_index": row_index}

        def _evaluate() -> None:
            if event.is_set() or getattr(self, "_early_stop_reason", None):
                return
            for plugin in plugins:
                try:
                    reason = plugin.check(record, metadata=metadata)
                except Exception:  # pragma: no cover - defensive guard
                    logger.exception(
                        "Early-stop plugin '%s' raised an unexpected error; continuing",
                        getattr(plugin, "name", "unknown"),
                    )
                    continue
                if not reason:
                    continue
                reason = dict(reason)
                reason.setdefault("plugin", getattr(plugin, "name", "unknown"))
                if metadata:
                    for key, value in metadata.items():
                        reason.setdefault(key, value)
                self._early_stop_reason = reason
                event.set()
                logger.info(
                    "Early stop triggered by plugin '%s' (reason: %s)",
                    reason.get("plugin", getattr(plugin, "name", "unknown")),
                    {k: v for k, v in reason.items() if k != "plugin"},
                )
                break

        lock: threading.Lock | None = getattr(self, "_early_stop_lock", None)
        if lock:
            with lock:
                _evaluate()
        else:
            _evaluate()


    def _process_single_row(
        self,
        engine: PromptEngine,
        system_template: PromptTemplate,
        user_template: PromptTemplate,
        criteria_templates: Dict[str, PromptTemplate],
        row_plugins: List[RowExperimentPlugin],
        context: Dict[str, Any],
        row: pd.Series,
        row_id: str | None,
    ) -> tuple[Dict[str, Any] | None, Dict[str, Any] | None]:
        if self._early_stop_event and self._early_stop_event.is_set():
            return None, None
        try:
            rendered_system_prompt = engine.render(system_template, context)
            if self.criteria:
                responses: Dict[str, Dict[str, Any]] = {}
                for crit in self.criteria:
                    crit_name = crit.get("name") or crit.get("template", "criteria")
                    prompt_template = criteria_templates[crit_name]
                    user_prompt = engine.render(prompt_template, context, extra={"criteria": crit_name})
                    response = self._execute_llm(
                        user_prompt,
                        {"row_id": row.get("APPID"), "criteria": crit_name},
                        system_prompt=rendered_system_prompt,
                    )
                    responses[crit_name] = response
                first_response = next(iter(responses.values())) if responses else {}
                record: Dict[str, Any] = {"row": context, "response": first_response, "responses": responses}
                for resp in responses.values():
                    metrics = resp.get("metrics")
                    if metrics:
                        record.setdefault("metrics", {}).update(metrics)
            else:
                user_prompt = engine.render(user_template, context)
                response = self._execute_llm(
                    user_prompt,
                    {"row_id": row.get("APPID")},
                    system_prompt=rendered_system_prompt,
                )
                record = {"row": context, "response": response}
                metrics = response.get("metrics")
                if metrics:
                    record.setdefault("metrics", {}).update(metrics)

            retry_meta = response.get("retry")
            if retry_meta:
                record["retry"] = retry_meta

            for plugin in row_plugins:
                derived = plugin.process_row(record["row"], record.get("responses") or {"default": record["response"]})
                if derived:
                    record.setdefault("metrics", {}).update(derived)
            if self._active_security_level:
                record["security_level"] = self._active_security_level
            return record, None
        except (PromptRenderingError, PromptValidationError) as exc:
            return None, {
                "row": context,
                "error": str(exc),
                "timestamp": time.time(),
            }
        except Exception as exc:  # pylint: disable=broad-except
            failure = {
                "row": context,
                "error": str(exc),
                "timestamp": time.time(),
            }
            history = getattr(exc, "_dmp_retry_history", None)
            if history:
                failure["retry"] = {
                    "attempts": getattr(exc, "_dmp_retry_attempts", len(history)),
                    "max_attempts": getattr(exc, "_dmp_retry_max_attempts", len(history)),
                    "history": history,
                }
            return None, failure

    def _should_run_parallel(self, config: Dict[str, Any], backlog_size: int) -> bool:
        if not config or not config.get("enabled"):
            return False
        max_workers = max(int(config.get("max_workers", 1)), 1)
        if max_workers <= 1:
            return False
        threshold = int(config.get("backlog_threshold", 50))
        return backlog_size >= threshold

    def _run_parallel(
        self,
        rows_to_process: List[tuple[int, pd.Series, Dict[str, Any], str | None]],
        engine: PromptEngine,
        system_template: PromptTemplate,
        user_template: PromptTemplate,
        criteria_templates: Dict[str, PromptTemplate],
        row_plugins: List[RowExperimentPlugin],
        handle_success,
        handle_failure,
        config: Dict[str, Any],
    ) -> None:
        max_workers = max(int(config.get("max_workers", 4)), 1)
        pause_threshold = float(config.get("utilization_pause", 0.8))
        pause_interval = float(config.get("pause_interval", 0.5))

        lock = threading.Lock()

        def worker(data: tuple[int, pd.Series, Dict[str, Any], str | None]) -> None:
            if self._early_stop_event and self._early_stop_event.is_set():
                return
            idx, row, context, row_id = data
            record, failure = self._process_single_row(
                engine,
                system_template,
                user_template,
                criteria_templates,
                row_plugins,
                context,
                row,
                row_id,
            )
            with lock:
                if record:
                    handle_success(idx, record, row_id)
                if failure:
                    handle_failure(failure)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for data in rows_to_process:
                if self.rate_limiter and pause_threshold > 0:
                    while True:
                        utilization = self.rate_limiter.utilization()
                        if utilization < pause_threshold:
                            break
                        time.sleep(pause_interval)
                if self._early_stop_event and self._early_stop_event.is_set():
                    break
                executor.submit(worker, data)

    def _build_sink_bindings(self) -> List[SinkBinding]:
        bindings: List[SinkBinding] = []
        for index, sink in enumerate(self.sinks):
            artifact_config = getattr(sink, "_dmp_artifact_config", {}) or {}
            plugin = getattr(sink, "_dmp_plugin_name", sink.__class__.__name__)
            base_id = getattr(sink, "_dmp_sink_name", plugin)
            sink_id = f"{base_id}:{index}"
            security_level = getattr(sink, "_dmp_security_level", None)
            if security_level is not None:
                security_level = normalize_security_level(security_level)
            bindings.append(
                SinkBinding(
                    id=sink_id,
                    plugin=plugin,
                    sink=sink,
                    artifact_config=artifact_config,
                    original_index=index,
                    security_level=security_level,
                )
            )
        return bindings

    def _execute_llm(self, user_prompt: str, metadata: Dict[str, Any], *, system_prompt: str | None = None) -> Dict[str, Any]:
        attempts = 1
        delay = 0.0
        max_attempts = 1
        backoff = 0.0
        if self.retry_config:
            max_attempts = int(self.retry_config.get("max_attempts", 1))
            delay = float(self.retry_config.get("initial_delay", 0.0))
            backoff = float(self.retry_config.get("backoff_multiplier", 1.0))

        attempt = 0
        last_error: Exception | None = None
        attempt_history: List[Dict[str, Any]] = []
        last_request: LLMRequest | None = None
        while attempt < max_attempts:
            attempt += 1
            try:
                request = LLMRequest(
                    system_prompt=system_prompt or self.prompt_system or "",
                    user_prompt=user_prompt,
                    metadata={**metadata, "attempt": attempt},
                )
                last_request = request
                attempt_start = time.time()
                for middleware in self.llm_middlewares or []:
                    request = middleware.before_request(request)

                if self.rate_limiter:
                    acquire_context = self.rate_limiter.acquire({"experiment": self.experiment_name, **request.metadata})
                else:
                    acquire_context = None

                if acquire_context:
                    with acquire_context:
                        response = self.llm_client.generate(
                            system_prompt=request.system_prompt,
                            user_prompt=request.user_prompt,
                            metadata=request.metadata,
                        )
                else:
                    response = self.llm_client.generate(
                        system_prompt=request.system_prompt,
                        user_prompt=request.user_prompt,
                        metadata=request.metadata,
                    )

                for middleware in reversed(self.llm_middlewares or []):
                    response = middleware.after_response(request, response)
                if self.cost_tracker:
                    cost_metrics = self.cost_tracker.record(response, {"experiment": self.experiment_name, **request.metadata})
                    if cost_metrics:
                        response.setdefault("metrics", {}).update(cost_metrics)
                attempt_record = {
                    "attempt": attempt,
                    "status": "success",
                    "duration": max(time.time() - attempt_start, 0.0),
                }
                attempt_history.append(attempt_record)
                response.setdefault("metrics", {})["attempts_used"] = attempt
                response.setdefault("retry", {
                    "attempts": attempt,
                    "max_attempts": max_attempts,
                    "history": attempt_history,
                })
                if self.rate_limiter:
                    self.rate_limiter.update_usage(response, request.metadata)
                return response
            except Exception as exc:  # pylint: disable=broad-except
                last_error = exc
                attempt_record = {
                    "attempt": attempt,
                    "status": "error",
                    "duration": max(time.time() - attempt_start, 0.0),
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                }
                if attempt >= max_attempts:
                    attempt_history.append(attempt_record)
                    break
                sleep_for = delay if delay > 0 else 0
                attempt_record["next_delay"] = sleep_for
                attempt_history.append(attempt_record)
                if sleep_for > 0:
                    time.sleep(sleep_for)
                if backoff and backoff > 0:
                    delay = delay * backoff if delay else backoff

        assert last_error is not None
        if last_request is not None:
            setattr(last_error, "_dmp_retry_history", attempt_history)
            setattr(last_error, "_dmp_retry_attempts", attempt)
            setattr(last_error, "_dmp_retry_max_attempts", max_attempts)
            try:
                self._notify_retry_exhausted(last_request, last_error, attempt_history)
            except Exception:  # pragma: no cover - defensive logging
                logger.debug("Retry exhausted hook raised", exc_info=True)
        raise last_error

    def _notify_retry_exhausted(self, request: LLMRequest, error: Exception, history: List[Dict[str, Any]]) -> None:
        metadata = {
            "experiment": self.experiment_name,
            "attempts": getattr(error, "_dmp_retry_attempts", len(history)),
            "max_attempts": getattr(error, "_dmp_retry_max_attempts", len(history)),
            "error": str(error),
            "error_type": error.__class__.__name__,
            "history": history,
        }
        logger.warning(
            "LLM request exhausted retries for experiment '%s' after %s attempts: %s",
            self.experiment_name,
            metadata["attempts"],
            metadata["error"],
        )
        for middleware in self.llm_middlewares or []:
            hook = getattr(middleware, "on_retry_exhausted", None)
            if callable(hook):
                try:
                    hook(request, metadata, error)
                except Exception:  # pragma: no cover - middleware isolation
                    logger.debug("Middleware %s retry hook failed", getattr(middleware, "name", middleware), exc_info=True)

    def _load_checkpoint(self, path: Path) -> set[str]:
        processed: set[str] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                processed.add(line)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
        return processed

    def _append_checkpoint(self, path: Path, row_id: str) -> None:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{row_id}\n")
