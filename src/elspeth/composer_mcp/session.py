"""Session persistence for the composer MCP server.

Sessions are stored as JSON files in the scratch directory.
Each file contains the serialized CompositionState (via to_dict/from_dict
round-trip) plus session metadata.

Layer: L3 (application). Imports from L3 (web.composer.state).
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from elspeth.web.composer.state import CompositionState, PipelineMetadata

# Tier-3 boundary: session_id arrives as an LLM-controlled MCP argument.
# The valid shape is the output of ``new_session`` — ``uuid.uuid4().hex[:12]``
# — a 12-character lowercase hex string. Anything else is either a client
# bug or a path-traversal attempt; either way, reject at the boundary
# rather than coerce (silent coercion would re-point the agent's intended
# session to a different file, a meaning-changing operation).
_SESSION_ID_RE = re.compile(r"^[a-f0-9]{12}$")


class InvalidSessionIdError(ValueError):
    """Raised when a session_id does not match the allowed shape.

    Subclasses ``ValueError`` so the MCP server's existing ``except
    (ValueError, KeyError, TypeError)`` handler at ``server.py`` surfaces
    it as a clean ``isError=True`` tool response without a stack trace.
    """

    def __init__(self, session_id: str) -> None:
        # The message echoes only the caller-supplied value — never a
        # server-side filesystem path — so no information is leaked back
        # to the LLM that it didn't already provide.
        super().__init__(f"Invalid session_id: {session_id!r}")
        self.session_id = session_id


def _validate_session_id(session_id: str) -> None:
    """Enforce the session_id shape at the filesystem boundary.

    Called from ``_session_path`` so every read/write/delete path inherits
    the guard automatically — a future method that calls ``_session_path``
    cannot accidentally bypass validation.

    The MCP tool schema declares ``session_id`` as ``"type": "string"``,
    so non-str inputs are a contract violation, not an attack. If one
    slips through, ``re.Pattern.fullmatch`` raises ``TypeError`` which
    the server's top-level handler converts to a clean tool error —
    equivalent security outcome, one fewer defensive branch.
    """
    if not _SESSION_ID_RE.fullmatch(session_id):
        raise InvalidSessionIdError(session_id)


class SessionNotFoundError(Exception):
    """Raised when a session ID does not correspond to a saved file."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session not found: {session_id}")
        self.session_id = session_id


class SessionManager:
    """Manages CompositionState sessions as JSON files on disk.

    Each session is a single JSON file: ``{scratch_dir}/{session_id}.json``.
    The file contains the full CompositionState serialized via to_dict().
    """

    def __init__(self, scratch_dir: Path) -> None:
        self._dir = scratch_dir

    def new_session(self, *, name: str = "Untitled Pipeline") -> tuple[str, CompositionState]:
        """Create a new empty session. Does not persist until save() is called."""
        session_id = uuid.uuid4().hex[:12]
        state = CompositionState(
            source=None,
            nodes=(),
            edges=(),
            outputs=(),
            metadata=PipelineMetadata(name=name),
            version=1,
        )
        return session_id, state

    def save(self, session_id: str, state: CompositionState) -> Path:
        """Persist session state to disk. Creates scratch dir if needed."""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._session_path(session_id)
        data = state.to_dict()
        path.write_text(json.dumps(data, indent=2, sort_keys=True))
        return path

    def load(self, session_id: str) -> CompositionState:
        """Load session state from disk."""
        path = self._session_path(session_id)
        if not path.exists():
            raise SessionNotFoundError(session_id)
        data = json.loads(path.read_text())
        return CompositionState.from_dict(data)

    def delete(self, session_id: str) -> None:
        """Delete a saved session."""
        path = self._session_path(session_id)
        if not path.exists():
            raise SessionNotFoundError(session_id)
        path.unlink()

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all saved sessions with ID, name, and version."""
        if not self._dir.exists():
            return []
        sessions: list[dict[str, Any]] = []
        for path in sorted(self._dir.glob("*.json")):
            data = json.loads(path.read_text())
            sessions.append(
                {
                    "session_id": path.stem,
                    "name": data["metadata"]["name"],
                    "version": data["version"],
                }
            )
        return sessions

    def _session_path(self, session_id: str) -> Path:
        # Chokepoint guard — every filesystem-touching method (save, load,
        # delete) routes here, so validating once covers all three.
        _validate_session_id(session_id)
        return self._dir / f"{session_id}.json"
