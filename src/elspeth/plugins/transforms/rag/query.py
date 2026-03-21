"""Query construction for RAG retrieval transform.

Three modes, all anchored on query_field:
1. Field only: use field value verbatim
2. Field + template: render Jinja2 template with {{ query }} and {{ row }}
3. Field + regex: extract search text via capture group
"""

from __future__ import annotations

import multiprocessing
import queue
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jinja2 import Template

from jinja2 import TemplateSyntaxError, UndefinedError
from jinja2.exceptions import SecurityError

from elspeth.plugins.infrastructure.templates import (
    TemplateError,
    create_sandboxed_environment,
)

# Fork context for regex subprocess — avoids spawn overhead on Linux and allows
# the worker process to be forcibly terminated (SIGTERM) when regex times out.
# spawn context cannot be used because the worker function is a closure and
# closures are not picklable across spawn boundaries.
_FORK_CTX = multiprocessing.get_context("fork")


def _regex_worker(
    pattern: re.Pattern[str],
    text: str,
    result_queue: multiprocessing.Queue,  # type: ignore[type-arg]
) -> None:
    """Run regex search in a child process and send picklable result to queue.

    Sends a 3-tuple: (matched: bool, group0: str | None, group1: str | None).
    re.Match objects are not picklable, so we extract the data before sending.
    """
    match = pattern.search(text)
    if match is None:
        result_queue.put((False, None, None))
    else:
        g0 = match.group(0)
        g1 = match.group(1) if pattern.groups else None
        result_queue.put((True, g0, g1))


@dataclass(frozen=True)
class QueryResult:
    """Result of query construction."""

    query: str | None = None
    error: dict[str, Any] | None = None


class QueryBuilder:
    """Constructs search queries from row data.

    Supports three modes:
    - Field only: query_field set, no template or pattern
    - Template: query_field + query_template (Jinja2)
    - Regex: query_field + query_pattern (re capture group)

    Regex mode spawns a child process per call to enforce the timeout deadline.
    Python threads cannot be interrupted while running C extension code (re module),
    so process-level isolation with SIGTERM is the only reliable timeout mechanism.
    """

    def __init__(
        self,
        query_field: str,
        *,
        query_template: str | None = None,
        query_pattern: str | None = None,
        regex_timeout: float = 5.0,
    ) -> None:
        self._query_field = query_field
        self._regex_timeout = regex_timeout
        self._compiled_template: Template | None = None
        self._compiled_pattern: re.Pattern[str] | None = None

        if query_template is not None:
            env = create_sandboxed_environment()
            try:
                self._compiled_template = env.from_string(query_template)
            except TemplateSyntaxError as e:
                raise TemplateError(f"Invalid query template syntax: {e}") from e

        if query_pattern is not None:
            self._compiled_pattern = re.compile(query_pattern)

    def build(self, row_data: dict[str, Any]) -> QueryResult:
        """Construct a search query from row data."""
        extracted = row_data[self._query_field]

        if extracted is None:
            return QueryResult(
                error={
                    "reason": "invalid_input",
                    "field": self._query_field,
                    "cause": "null_value",
                }
            )

        if self._compiled_template is not None:
            return self._build_template(extracted, row_data)
        elif self._compiled_pattern is not None:
            return self._build_regex(extracted)
        else:
            return self._build_field_only(extracted)

    def _build_field_only(self, extracted: Any) -> QueryResult:
        if not isinstance(extracted, str):
            raise TypeError(
                f"query_field '{self._query_field}' expected str, got {type(extracted).__name__} "
                f"— upstream plugin bug (Tier 2 data must not be coerced)"
            )
        return self._validate_non_empty(extracted)

    def _build_template(self, extracted: Any, row_data: dict[str, Any]) -> QueryResult:
        assert self._compiled_template is not None  # guaranteed by build() guard
        try:
            query = self._compiled_template.render(query=extracted, row=row_data)
        except (UndefinedError, SecurityError, OverflowError, ZeroDivisionError, ArithmeticError, TypeError, ValueError) as e:
            return QueryResult(
                error={
                    "reason": "template_rendering_failed",
                    "error": str(e),
                    "field": self._query_field,
                }
            )
        return self._validate_non_empty(query)

    def _build_regex(self, extracted: Any) -> QueryResult:
        assert self._compiled_pattern is not None  # guaranteed by build() guard
        if not isinstance(extracted, str):
            raise TypeError(
                f"query_field '{self._query_field}' expected str, got {type(extracted).__name__} "
                f"— upstream plugin bug (Tier 2 data must not be coerced)"
            )
        text = extracted
        result_queue: multiprocessing.Queue = _FORK_CTX.Queue()  # type: ignore[type-arg]
        try:
            return self._run_regex_subprocess(text, result_queue)
        finally:
            result_queue.close()
            result_queue.join_thread()

    def _run_regex_subprocess(
        self,
        text: str,
        result_queue: multiprocessing.Queue,  # type: ignore[type-arg]
    ) -> QueryResult:
        """Execute regex in subprocess and interpret result.

        Separated from _build_regex to keep the try/finally cleanup clean.
        """
        assert self._compiled_pattern is not None
        p = _FORK_CTX.Process(
            target=_regex_worker,
            args=(self._compiled_pattern, text, result_queue),
        )
        p.start()
        p.join(timeout=self._regex_timeout)

        if p.is_alive():
            p.terminate()
            p.join()
            return QueryResult(
                error={
                    "reason": "no_regex_match",
                    "field": self._query_field,
                    "cause": "regex_timeout",
                }
            )

        # Check for subprocess crash BEFORE reading the queue.
        # _regex_worker is system-owned code — a crash is a code bug, not a data issue.
        # Per offensive programming rules: plugin bugs crash, they don't quarantine.
        if p.exitcode != 0:
            raise RuntimeError(
                f"Regex worker subprocess crashed with exitcode {p.exitcode} "
                f"while evaluating pattern {self._compiled_pattern.pattern!r} "
                f"against field '{self._query_field}'. This is a bug in the regex "
                f"worker or the Python regex engine — not a data issue."
            )

        try:
            matched, group0, group1 = result_queue.get_nowait()
        except queue.Empty as exc:
            # exitcode == 0 but queue empty — _regex_worker completed without
            # putting a result. This should be impossible if _regex_worker is
            # correct — it always puts exactly one tuple. Crash, don't fabricate.
            raise RuntimeError(
                f"Regex worker subprocess exited cleanly (exitcode 0) but produced "
                f"no result for pattern {self._compiled_pattern.pattern!r} on field "
                f"'{self._query_field}'. This is a bug in _regex_worker — it must "
                f"always put exactly one result on the queue."
            ) from exc

        if not matched:
            return QueryResult(
                error={
                    "reason": "no_regex_match",
                    "field": self._query_field,
                    "pattern": self._compiled_pattern.pattern,
                }
            )

        # Use group1 if the pattern has capture groups (may be None if non-participating)
        captured = group1 if self._compiled_pattern.groups else group0
        if captured is None:
            return QueryResult(
                error={
                    "reason": "no_regex_match",
                    "field": self._query_field,
                    "cause": "capture_group_empty",
                }
            )

        return self._validate_non_empty(captured)

    def _validate_non_empty(self, query: str) -> QueryResult:
        if not query.strip():
            return QueryResult(
                error={
                    "reason": "invalid_input",
                    "field": self._query_field,
                    "cause": "empty_query",
                }
            )
        return QueryResult(query=query)

    def close(self) -> None:
        """No-op. Retained for API symmetry — no persistent resources to release."""
