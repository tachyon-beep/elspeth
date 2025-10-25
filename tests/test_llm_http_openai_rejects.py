from __future__ import annotations

import pytest

from elspeth.core.base.types import SecurityLevel
from elspeth.plugins.nodes.transforms.llm.openai_http import HttpOpenAIClient


def test_http_openai_rejects_non_local_http_endpoint():
    # Non-local HTTP endpoints must be rejected by endpoint validation
    with pytest.raises(ValueError):
        HttpOpenAIClient(
            security_level=SecurityLevel.UNOFFICIAL,
            allow_downgrade=True,
            api_base="http://example.com",
            model="test"
        )
