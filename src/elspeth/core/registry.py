"""Simple registry for resolving plugin implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping

from elspeth.core.interfaces import DataSource, LLMClientProtocol, ResultSink
from elspeth.core.validation import ConfigurationError, validate_schema
from elspeth.plugins.datasources import BlobDataSource, CSVBlobDataSource, CSVDataSource
from elspeth.plugins.llms import AzureOpenAIClient, HttpOpenAIClient, MockLLMClient
from elspeth.plugins.outputs import (
    AnalyticsReportSink,
    AzureDevOpsRepoSink,
    BlobResultSink,
    CsvResultSink,
    ExcelResultSink,
    FileCopySink,
    GitHubRepoSink,
    LocalBundleSink,
    SignedArtifactSink,
    ZipResultSink,
)

ON_ERROR_ENUM = {"type": "string", "enum": ["abort", "skip"]}

ARTIFACT_DESCRIPTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "type": {"type": "string"},
        "schema_id": {"type": "string"},
        "persist": {"type": "boolean"},
        "alias": {"type": "string"},
        "security_level": {"type": "string"},
    },
    "required": ["name", "type"],
    "additionalProperties": False,
}

ARTIFACTS_SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "produces": {
            "type": "array",
            "items": ARTIFACT_DESCRIPTOR_SCHEMA,
        },
        "consumes": {
            "type": "array",
            "items": {
                "oneOf": [
                    {"type": "string"},
                    {
                        "type": "object",
                        "properties": {
                            "token": {"type": "string"},
                            "mode": {"type": "string", "enum": ["single", "all"]},
                        },
                        "required": ["token"],
                        "additionalProperties": False,
                    },
                ]
            },
        },
    },
    "additionalProperties": False,
}


@dataclass
class PluginFactory:
    """Factory metadata holding creation callable and validation schema."""

    create: Callable[[Dict[str, Any]], Any]
    schema: Mapping[str, Any] | None = None

    def validate(self, options: Dict[str, Any], context: str) -> None:
        """Validate options against the schema, raising ConfigurationError on failure."""

        if self.schema is None:
            return
        errors = list(validate_schema(options or {}, self.schema, context=context))
        if errors:
            message = "\n".join(msg.format() for msg in errors)
            raise ConfigurationError(message)


class PluginRegistry:
    """Central registry for datasource, LLM, and sink plugins."""

    def __init__(self):
        self._datasources: Dict[str, PluginFactory] = {
            "azure_blob": PluginFactory(
                create=lambda options: BlobDataSource(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "config_path": {"type": "string"},
                        "profile": {"type": "string"},
                        "pandas_kwargs": {"type": "object"},
                        "on_error": ON_ERROR_ENUM,
                        "security_level": {"type": "string"},
                    },
                    "required": ["config_path"],
                    "additionalProperties": True,
                },
            ),
            "csv_blob": PluginFactory(
                create=lambda options: CSVBlobDataSource(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "dtype": {"type": "object"},
                        "encoding": {"type": "string"},
                        "on_error": ON_ERROR_ENUM,
                        "security_level": {"type": "string"},
                    },
                    "required": ["path"],
                    "additionalProperties": True,
                },
            ),
            "local_csv": PluginFactory(
                create=lambda options: CSVDataSource(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "dtype": {"type": "object"},
                        "encoding": {"type": "string"},
                        "on_error": ON_ERROR_ENUM,
                        "security_level": {"type": "string"},
                    },
                    "required": ["path"],
                    "additionalProperties": True,
                },
            ),
        }
        self._llms: Dict[str, PluginFactory] = {
            "azure_openai": PluginFactory(
                create=lambda options: AzureOpenAIClient(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "config": {"type": "object"},
                        "deployment": {"type": "string"},
                        "client": {},
                    },
                    "required": ["config"],
                    "additionalProperties": True,
                },
            ),
            "http_openai": PluginFactory(
                create=lambda options: HttpOpenAIClient(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "api_base": {"type": "string"},
                        "api_key": {"type": "string"},
                        "api_key_env": {"type": "string"},
                        "model": {"type": "string"},
                        "temperature": {"type": "number"},
                        "max_tokens": {"type": "integer"},
                        "timeout": {"type": "number", "exclusiveMinimum": 0},
                    },
                    "required": ["api_base"],
                    "additionalProperties": True,
                },
            ),
            "mock": PluginFactory(
                create=lambda options: MockLLMClient(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "seed": {"type": "integer"},
                    },
                    "additionalProperties": True,
                },
            ),
        }
        self._sinks: Dict[str, PluginFactory] = {
            "azure_blob": PluginFactory(
                create=lambda options: BlobResultSink(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "config_path": {"type": "string"},
                        "profile": {"type": "string"},
                        "path_template": {"type": "string"},
                        "filename": {"type": "string"},
                        "manifest_template": {"type": "string"},
                        "manifest_suffix": {"type": "string"},
                        "include_manifest": {"type": "boolean"},
                        "overwrite": {"type": "boolean"},
                        "metadata": {"type": "object"},
                        "upload_chunk_size": {"type": "integer", "minimum": 0},
                        "credential": {},
                        "credential_env": {"type": "string"},
                        "content_type": {"type": "string"},
                        "artifacts": ARTIFACTS_SECTION_SCHEMA,
                        "security_level": {"type": "string"},
                        "on_error": ON_ERROR_ENUM,
                    },
                    "required": ["config_path"],
                    "additionalProperties": True,
                },
            ),
            "csv": PluginFactory(
                create=lambda options: CsvResultSink(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "overwrite": {"type": "boolean"},
                        "sanitize_formulas": {"type": "boolean"},
                        "sanitize_guard": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 1,
                        },
                        "artifacts": ARTIFACTS_SECTION_SCHEMA,
                        "security_level": {"type": "string"},
                        "on_error": ON_ERROR_ENUM,
                    },
                    "required": ["path"],
                    "additionalProperties": True,
                },
            ),
            "local_bundle": PluginFactory(
                create=lambda options: LocalBundleSink(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "base_path": {"type": "string"},
                        "bundle_name": {"type": "string"},
                        "timestamped": {"type": "boolean"},
                        "write_json": {"type": "boolean"},
                        "write_csv": {"type": "boolean"},
                        "sanitize_formulas": {"type": "boolean"},
                        "sanitize_guard": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 1,
                        },
                        "artifacts": ARTIFACTS_SECTION_SCHEMA,
                        "security_level": {"type": "string"},
                        "on_error": ON_ERROR_ENUM,
                    },
                    "required": ["base_path"],
                    "additionalProperties": True,
                },
            ),
            "excel_workbook": PluginFactory(
                create=lambda options: ExcelResultSink(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "base_path": {"type": "string"},
                        "workbook_name": {"type": "string"},
                        "timestamped": {"type": "boolean"},
                        "results_sheet": {"type": "string"},
                        "manifest_sheet": {"type": "string"},
                        "aggregates_sheet": {"type": "string"},
                        "include_manifest": {"type": "boolean"},
                        "include_aggregates": {"type": "boolean"},
                        "sanitize_formulas": {"type": "boolean"},
                        "sanitize_guard": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 1,
                        },
                        "artifacts": ARTIFACTS_SECTION_SCHEMA,
                        "security_level": {"type": "string"},
                        "on_error": ON_ERROR_ENUM,
                    },
                    "required": ["base_path"],
                    "additionalProperties": True,
                },
            ),
            "zip_bundle": PluginFactory(
                create=lambda options: ZipResultSink(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "base_path": {"type": "string"},
                        "bundle_name": {"type": "string"},
                        "timestamped": {"type": "boolean"},
                        "include_manifest": {"type": "boolean"},
                        "include_results": {"type": "boolean"},
                        "include_csv": {"type": "boolean"},
                        "manifest_name": {"type": "string"},
                        "results_name": {"type": "string"},
                        "csv_name": {"type": "string"},
                        "artifacts": ARTIFACTS_SECTION_SCHEMA,
                        "security_level": {"type": "string"},
                        "on_error": ON_ERROR_ENUM,
                    },
                    "required": ["base_path"],
                    "additionalProperties": True,
                },
            ),
            "file_copy": PluginFactory(
                create=lambda options: FileCopySink(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "destination": {"type": "string"},
                        "overwrite": {"type": "boolean"},
                        "artifacts": ARTIFACTS_SECTION_SCHEMA,
                        "security_level": {"type": "string"},
                        "on_error": ON_ERROR_ENUM,
                    },
                    "required": ["destination"],
                    "additionalProperties": True,
                },
            ),
            "github_repo": PluginFactory(
                create=lambda options: GitHubRepoSink(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "path_template": {"type": "string"},
                        "commit_message_template": {"type": "string"},
                        "include_manifest": {"type": "boolean"},
                        "owner": {"type": "string"},
                        "repo": {"type": "string"},
                        "branch": {"type": "string"},
                        "token_env": {"type": "string"},
                        "dry_run": {"type": "boolean"},
                        "artifacts": ARTIFACTS_SECTION_SCHEMA,
                        "security_level": {"type": "string"},
                        "on_error": ON_ERROR_ENUM,
                    },
                    "required": ["owner", "repo"],
                    "additionalProperties": True,
                },
            ),
            "azure_devops_repo": PluginFactory(
                create=lambda options: AzureDevOpsRepoSink(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "path_template": {"type": "string"},
                        "commit_message_template": {"type": "string"},
                        "include_manifest": {"type": "boolean"},
                        "organization": {"type": "string"},
                        "project": {"type": "string"},
                        "repository": {"type": "string"},
                        "branch": {"type": "string"},
                        "token_env": {"type": "string"},
                        "api_version": {"type": "string"},
                        "base_url": {"type": "string"},
                        "dry_run": {"type": "boolean"},
                        "artifacts": ARTIFACTS_SECTION_SCHEMA,
                        "security_level": {"type": "string"},
                        "on_error": ON_ERROR_ENUM,
                    },
                    "required": ["organization", "project", "repository"],
                    "additionalProperties": True,
                },
            ),
            "signed_artifact": PluginFactory(
                create=lambda options: SignedArtifactSink(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "base_path": {"type": "string"},
                        "bundle_name": {"type": "string"},
                        "key": {"type": "string"},
                        "key_env": {"type": "string"},
                        "hash_algorithm": {"type": "string"},
                        "security_level": {"type": "string"},
                        "artifacts": ARTIFACTS_SECTION_SCHEMA,
                        "on_error": ON_ERROR_ENUM,
                    },
                    "required": ["base_path"],
                    "additionalProperties": True,
                },
            ),
            "analytics_report": PluginFactory(
                create=lambda options: AnalyticsReportSink(**options),
                schema={
                    "type": "object",
                    "properties": {
                        "base_path": {"type": "string"},
                        "file_stem": {"type": "string"},
                        "formats": {
                            "type": "array",
                            "items": {"type": "string", "enum": ["json", "md", "markdown"]},
                        },
                        "include_metadata": {"type": "boolean"},
                        "include_aggregates": {"type": "boolean"},
                        "include_comparisons": {"type": "boolean"},
                        "artifacts": ARTIFACTS_SECTION_SCHEMA,
                        "security_level": {"type": "string"},
                        "on_error": ON_ERROR_ENUM,
                    },
                    "required": ["base_path"],
                    "additionalProperties": True,
                },
            ),
        }

    def create_datasource(self, name: str, options: Dict[str, Any]) -> DataSource:
        """Instantiate a datasource plugin by name after validating options."""

        try:
            factory = self._datasources[name]
        except KeyError as exc:
            raise ValueError(f"Unknown datasource plugin '{name}'") from exc
        factory.validate(options or {}, context=f"datasource:{name}")
        return factory.create(options)

    def validate_datasource(self, name: str, options: Dict[str, Any] | None) -> None:
        """Validate datasource plugin options without creating the plugin."""

        try:
            factory = self._datasources[name]
        except KeyError as exc:
            raise ValueError(f"Unknown datasource plugin '{name}'") from exc
        factory.validate(options or {}, context=f"datasource:{name}")

    def create_llm(self, name: str, options: Dict[str, Any]) -> LLMClientProtocol:
        """Instantiate an LLM plugin by name after validating options."""

        try:
            factory = self._llms[name]
        except KeyError as exc:
            raise ValueError(f"Unknown llm plugin '{name}'") from exc
        factory.validate(options or {}, context=f"llm:{name}")
        return factory.create(options)

    def validate_llm(self, name: str, options: Dict[str, Any] | None) -> None:
        """Validate LLM plugin options without instantiation."""

        try:
            factory = self._llms[name]
        except KeyError as exc:
            raise ValueError(f"Unknown llm plugin '{name}'") from exc
        factory.validate(options or {}, context=f"llm:{name}")

    def create_sink(self, name: str, options: Dict[str, Any]) -> ResultSink:
        """Instantiate a sink plugin by name after validating options."""

        try:
            factory = self._sinks[name]
        except KeyError as exc:
            raise ValueError(f"Unknown sink plugin '{name}'") from exc
        factory.validate(options or {}, context=f"sink:{name}")
        return factory.create(options)

    def validate_sink(self, name: str, options: Dict[str, Any] | None) -> None:
        """Validate sink plugin options without instantiation."""

        try:
            factory = self._sinks[name]
        except KeyError as exc:
            raise ValueError(f"Unknown sink plugin '{name}'") from exc
        factory.validate(options or {}, context=f"sink:{name}")


registry = PluginRegistry()
