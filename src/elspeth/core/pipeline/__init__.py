"""Artifact processing pipeline utilities."""

from elspeth.core.base.protocols import Artifact, ArtifactDescriptor

from .artifact_pipeline import ArtifactPipeline
from .processing import prepare_prompt_context

__all__ = ["ArtifactPipeline", "Artifact", "ArtifactDescriptor", "prepare_prompt_context"]
