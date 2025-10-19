"""Artifact dependency resolution for result sinks."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, cast

from elspeth.core.base.protocols import Artifact, ArtifactDescriptor, ResultSink
from elspeth.core.pipeline.artifacts import validate_artifact_type
from elspeth.core.security import is_security_level_allowed, normalize_security_level

VALID_REQUEST_MODES = {"single", "all"}
logger = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
@dataclass
class ArtifactRequest:
    """Declarative request describing how a sink consumes artifacts."""

    token: str
    mode: str = "single"


class ArtifactRequestParser:
    """Parsing helpers for artifact consumption declarations."""

    @staticmethod
    def parse(entry: Any) -> ArtifactRequest:
        """Convert configuration entries into `ArtifactRequest` objects."""

        if isinstance(entry, ArtifactRequest):
            ArtifactRequestParser._validate(entry.mode)
            return entry
        if isinstance(entry, str):
            ArtifactRequestParser._validate("single")
            return ArtifactRequest(token=entry, mode="single")
        if isinstance(entry, Mapping):
            token = entry.get("token") or entry.get("name")
            if not token:
                raise ValueError("Artifact consume entry requires 'token'")
            mode = entry.get("mode", "single")
            ArtifactRequestParser._validate(mode)
            return ArtifactRequest(token=token, mode=mode)
        raise ValueError(f"Unsupported consume declaration: {entry!r}")

    @staticmethod
    def _validate(mode: str) -> None:
        """Ensure request mode is one of the supported options."""

        if mode not in VALID_REQUEST_MODES:
            raise ValueError(f"Unsupported artifact request mode '{mode}'")


# pylint: disable=too-many-instance-attributes
@dataclass
class SinkBinding:
    """Container tying a sink instance to its configuration metadata."""

    id: str
    plugin: str
    sink: ResultSink
    artifact_config: dict[str, Any]
    original_index: int
    produces: list[ArtifactDescriptor] = field(default_factory=list)
    consumes: list[ArtifactRequest] = field(default_factory=list)
    security_level: str | None = None


# pylint: disable=too-few-public-methods
class ArtifactStore:
    """Holds produced artifacts for downstream sinks."""

    def __init__(self) -> None:
        """Initialise internal indexes for artifact lookups."""

        self._by_id: dict[str, Artifact] = {}
        self._by_alias: dict[str, Artifact] = {}
        self._by_type: dict[str, list[Artifact]] = defaultdict(list)

    def register(self, binding: SinkBinding, descriptor: ArtifactDescriptor, artifact: Artifact) -> None:
        """Record an artifact emitted by `binding` under the descriptor metadata."""

        artifact_id = artifact.id or f"{binding.id}:{descriptor.name}"
        artifact.id = artifact_id
        artifact.produced_by = binding.id
        artifact.persist = descriptor.persist or artifact.persist
        artifact.schema_id = artifact.schema_id or descriptor.schema_id
        level = artifact.security_level or descriptor.security_level or binding.security_level
        artifact.security_level = normalize_security_level(level)
        self._by_id[artifact_id] = artifact

        alias_key = descriptor.alias or descriptor.name
        if alias_key:
            self._by_alias[alias_key] = artifact

        self._by_type[descriptor.type].append(artifact)

    def get_by_alias(self, alias: str) -> Artifact | None:
        """Look up an artifact via its alias."""

        return self._by_alias.get(alias)

    def get_by_type(self, type_name: str) -> list[Artifact]:
        """Return all artifacts matching a specific type."""

        return list(self._by_type.get(type_name, []))

    def resolve_requests(self, requests: Iterable[ArtifactRequest]) -> dict[str, list[Artifact]]:
        """Resolve a list of artifact requests into concrete artifact results."""

        resolved: dict[str, list[Artifact]] = {}
        for request in requests:
            token = request.token
            if not token:
                continue
            selected: list[Artifact] = []
            if token.startswith("@"):  # alias lookup
                alias = token[1:]
                artifact = self.get_by_alias(alias)
                if artifact is not None:
                    selected.append(artifact)
            else:
                try:
                    validate_artifact_type(token)
                except ValueError:
                    continue
                selected = self.get_by_type(token)

            if request.mode == "single" and selected:
                selected = selected[:1]

            key = token
            resolved[key] = selected
            if token.startswith("@"):  # convenience alias without '@'
                resolved[token[1:]] = selected
        return resolved

    def items(self) -> Iterable[tuple[str, Artifact]]:
        """Yield stored artifacts keyed by their canonical identifier."""

        return self._by_id.items()


class ArtifactPipeline:  # pylint: disable=too-many-instance-attributes
    """Resolves sink execution order based on declared artifact dependencies."""

    def __init__(self, bindings: list[SinkBinding]) -> None:
        """Prepare bindings and calculate execution order."""

        self._bindings = [self._prepare_binding(binding) for binding in bindings]
        self._ordered_bindings = self._resolve_order(self._bindings)

    @staticmethod
    def _prepare_binding(binding: SinkBinding) -> SinkBinding:
        """Populate sink binding metadata from configuration and sink methods."""

        if binding.security_level is None or not str(binding.security_level).strip():
            raise ValueError(f"Sink '{binding.id}' must declare a security_level")
        binding.security_level = normalize_security_level(binding.security_level)
        artifact_section = binding.artifact_config or {}
        produces_config = artifact_section.get("produces", []) or []
        for entry in produces_config:
            descriptor = ArtifactDescriptor(
                name=entry["name"],
                type=entry["type"],
                schema_id=entry.get("schema_id"),
                persist=entry.get("persist", False),
                alias=entry.get("alias"),
                security_level=normalize_security_level(entry.get("security_level")),
            )
            validate_artifact_type(descriptor.type)
            binding.produces.append(descriptor)

        produces_method = getattr(binding.sink, "produces", None)
        if callable(produces_method):
            produced_iterable = produces_method()
            if produced_iterable:
                for descriptor in cast(Iterable[ArtifactDescriptor], produced_iterable):
                    validate_artifact_type(descriptor.type)
                    descriptor.security_level = normalize_security_level(descriptor.security_level)
                    binding.produces.append(descriptor)

        consumes_config = list(artifact_section.get("consumes", []) or [])
        consumes_method = getattr(binding.sink, "consumes", None)
        if callable(consumes_method):
            consumed_tokens = consumes_method()
            if consumed_tokens:
                consumes_config.extend(cast(Iterable[str], consumed_tokens))
        binding.consumes = [ArtifactRequestParser.parse(entry) for entry in consumes_config]
        return binding

    @staticmethod
    def _enforce_dependency_security(consumer: SinkBinding, producer: SinkBinding) -> None:
        """Ensure a consumer is allowed to read artifacts produced by the producer."""

        if not consumer.security_level:
            return
        if not is_security_level_allowed(producer.security_level, consumer.security_level):
            raise PermissionError(f"Sink '{consumer.id}' cannot depend on '{producer.id}' due to security level mismatch")

    @staticmethod
    def _resolve_order(bindings: list[SinkBinding]) -> list[SinkBinding]:
        """Topologically sort bindings based on artifact dependencies."""

        if not bindings:
            return []

        by_id = {binding.id: binding for binding in bindings}
        producers_by_name, producers_by_type = ArtifactPipeline._build_producer_indexes(bindings)
        dependencies, dependents = ArtifactPipeline._build_dependency_graph(bindings, producers_by_name, producers_by_type)
        ordered = ArtifactPipeline._topological_sort(bindings, dependencies, dependents, by_id)

        if len(ordered) != len(bindings):
            raise ValueError("Sink artifact dependencies contain a cycle or unresolved reference")

        return ordered

    @staticmethod
    def _build_producer_indexes(bindings: Iterable[SinkBinding]) -> tuple[dict[str, SinkBinding], dict[str, list[SinkBinding]]]:
        """Index bindings by produced alias/name and artifact type."""

        producers_by_name: dict[str, SinkBinding] = {}
        producers_by_type: dict[str, list[SinkBinding]] = defaultdict(list)

        for binding in bindings:
            for descriptor in binding.produces:
                key = descriptor.alias or descriptor.name
                if key and key not in producers_by_name:
                    producers_by_name[key] = binding
                producers_by_type[descriptor.type].append(binding)

        return producers_by_name, producers_by_type

    @staticmethod
    def _iter_producers_for_request(
        consumer: SinkBinding,
        request: ArtifactRequest,
        producers_by_name: dict[str, SinkBinding],
        producers_by_type: dict[str, list[SinkBinding]],
    ) -> Iterable[SinkBinding]:
        """Yield producer bindings that satisfy a consume request."""

        token = request.token
        if not token:
            return []

        if token.startswith("@"):
            key = token[1:]
            producer = producers_by_name.get(key)
            if producer:
                ArtifactPipeline._enforce_dependency_security(consumer, producer)
                return [producer]
            return []

        try:
            validate_artifact_type(token)
        except ValueError:
            return []

        matches: list[SinkBinding] = []
        for producer in producers_by_type.get(token, []):
            ArtifactPipeline._enforce_dependency_security(consumer, producer)
            matches.append(producer)
        return matches

    @staticmethod
    def _build_dependency_graph(
        bindings: Iterable[SinkBinding],
        producers_by_name: dict[str, SinkBinding],
        producers_by_type: dict[str, list[SinkBinding]],
    ) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        """Map dependencies and dependents between bindings."""

        dependencies: dict[str, set[str]] = {binding.id: set() for binding in bindings}
        dependents: dict[str, set[str]] = {binding.id: set() for binding in bindings}

        for binding in bindings:
            for request in binding.consumes:
                for producer in ArtifactPipeline._iter_producers_for_request(binding, request, producers_by_name, producers_by_type):
                    if producer.id == binding.id:
                        continue
                    dependencies[binding.id].add(producer.id)
                    dependents[producer.id].add(binding.id)

        return dependencies, dependents

    @staticmethod
    def _topological_sort(
        bindings: Iterable[SinkBinding],
        dependencies: dict[str, set[str]],
        dependents: dict[str, set[str]],
        by_id: dict[str, SinkBinding],
    ) -> list[SinkBinding]:
        """Order bindings based on resolved dependencies."""

        ready: deque[SinkBinding] = deque(
            sorted(
                [binding for binding in bindings if not dependencies[binding.id]],
                key=lambda b: b.original_index,
            )
        )

        ordered: list[SinkBinding] = []

        while ready:
            current = ready.popleft()
            ordered.append(current)
            for dependent_id in dependents[current.id]:
                deps = dependencies[dependent_id]
                if current.id not in deps:
                    continue
                deps.remove(current.id)
                if deps:
                    continue
                ready.append(by_id[dependent_id])
                ready = deque(sorted(ready, key=lambda b: b.original_index))

        return ordered

    # pylint: disable=too-many-locals
    def execute(
        self,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        *,
        on_error: str = "raise",
        failures: list[dict[str, Any]] | None = None,
    ) -> ArtifactStore:
        """Run all sinks in dependency order, producing the final artifact store.

        Args:
            payload: Experiment/job payload passed to sinks
            metadata: Metadata to pass alongside payload
            on_error: Error handling strategy: "raise" (default) or "continue"
            failures: Optional list to append failure dicts when continuing on errors

        Returns:
            ArtifactStore with all registered artifacts
        """

        if on_error not in {"raise", "continue"}:  # pragma: no cover - defensive guard
            raise ValueError("on_error must be 'raise' or 'continue'")

        store = ArtifactStore()
        metadata_dict: dict[str, Any | None] = dict(metadata) if metadata is not None else {}
        for binding in self._ordered_bindings:
            try:
                consumed = store.resolve_requests(binding.consumes)

                clearance = binding.security_level
                if clearance:
                    for artifacts in consumed.values():
                        for artifact in artifacts:
                            if not is_security_level_allowed(artifact.security_level, clearance):
                                raise PermissionError(
                                    f"Sink '{binding.id}' with clearance '{clearance}' cannot consume "
                                    f"artifact '{artifact.id}' at level '{normalize_security_level(artifact.security_level)}'"
                                )

                prepare = getattr(binding.sink, "prepare_artifacts", None)
                if callable(prepare):
                    prepare(consumed)

                binding.sink.write(payload, metadata=metadata_dict)

                produced: dict[str, Artifact] = {}
                collector = getattr(binding.sink, "collect_artifacts", None)
                if callable(collector):
                    collected = collector()
                    if collected:
                        produced = cast(dict[str, Artifact], collected)

                for descriptor in binding.produces:
                    key = descriptor.name
                    candidate = produced.get(key)
                    if not candidate and descriptor.alias:
                        candidate = produced.get(descriptor.alias)
                    if candidate:
                        store.register(binding, descriptor, candidate)

                finalize = getattr(binding.sink, "finalize", None)
                if callable(finalize):
                    finalize(dict(store.items()), metadata=metadata_dict)
            except Exception as exc:  # pylint: disable=broad-except
                if on_error == "continue":
                    sink_name = getattr(getattr(binding.sink, "__class__", type(binding.sink)), "__name__", binding.plugin or binding.id)
                    failure = {"sink": sink_name, "error": str(exc)}
                    if failures is not None:
                        failures.append(failure)
                    # Continue to next binding to maximize delivery
                    continue
                raise

        return store
