"""Pydantic request/response schemas for the secrets REST API.

SECURITY: No schema in this module may ever carry a plaintext secret value
in a response model.  ``CreateSecretRequest`` accepts a value on the way *in*;
``CreateSecretResponse`` deliberately omits it on the way *out*.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from elspeth.web.validation import has_visible_content


class SecretInventoryResponse(BaseModel):
    """Public metadata for a secret reference -- NEVER includes the value."""

    name: str
    scope: str
    available: bool
    source_kind: str = ""


class CreateSecretRequest(BaseModel):
    """Write-only request body for creating/updating a user-scoped secret."""

    name: str = Field(min_length=1, max_length=256, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    value: str = Field(min_length=1, max_length=65536)

    @field_validator("value")
    @classmethod
    def reject_invisible_only(cls, v: str) -> str:
        if not has_visible_content(v):
            raise ValueError("Secret value must contain at least one visible character")
        return v


class CreateSecretResponse(BaseModel):
    """Write-only acknowledgement -- NEVER includes the value."""

    name: str
    scope: str
    available: bool


class ValidateSecretResponse(BaseModel):
    """Existence check -- confirms whether a named secret is resolvable."""

    name: str
    available: bool
