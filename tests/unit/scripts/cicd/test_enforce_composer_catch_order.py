"""Tests for enforce_composer_catch_order.py.

Verifies the CI gate detects inverted except-handler order for
``ComposerServiceError`` / ``ComposerPluginCrashError`` (and any other
declared subclass→supertype pair) and accepts correct narrow-first order.

Co-located with the other CI-enforcer tests at tests/unit/scripts/cicd/ —
mirrors test_enforce_composer_exception_channel.py.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(extra_args: list[str]) -> subprocess.CompletedProcess[str]:
    """Invoke the enforcer as a module, with cwd set to the project root."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.cicd.enforce_composer_catch_order",
            *extra_args,
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[4]),  # project root
    )


def _make_routes_tree(tmp_path: Path, body: str) -> Path:
    """Create a fake src layout so the canonical-target assertion holds.

    Layout created:
        tmp_path/web/sessions/routes.py
    The enforcer is invoked with --root tmp_path (test-mode), so
    ``relative_to(root)`` yields ``"web/sessions/routes.py"``.
    """
    target_dir = tmp_path / "web" / "sessions"
    target_dir.mkdir(parents=True)
    target = target_dir / "routes.py"
    target.write_text(body)
    return target


class TestComposerCatchOrderEnforcer:
    def test_narrow_before_broad_passes(self, tmp_path: Path) -> None:
        """Correct order — subclass first, then supertype — is accepted.

        This is the canonical pattern in web/sessions/routes.py at
        lines 483 and 625. The test fixes the rule's green path so future
        refactors cannot quietly strip the ordering by coincidence.
        """
        _make_routes_tree(
            tmp_path,
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except ComposerPluginCrashError as crash:\n"
            "        pass\n"
            "    except ComposerServiceError as exc:\n"
            "        pass\n",
        )
        result = _run(["check", "--root", str(tmp_path)])
        assert result.returncode == 0, result.stdout + result.stderr

    def test_inverted_order_fails(self, tmp_path: Path) -> None:
        """Supertype handler before subclass handler makes the subclass
        handler unreachable — fail the build with CCO1."""
        _make_routes_tree(
            tmp_path,
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except ComposerServiceError as exc:\n"
            "        pass\n"
            "    except ComposerPluginCrashError as crash:\n"
            "        pass\n",
        )
        result = _run(["check", "--root", str(tmp_path)])
        assert result.returncode != 0
        assert "CCO1" in result.stdout
        assert "ComposerPluginCrashError" in result.stdout

    def test_inverted_order_flags_sibling_module(self, tmp_path: Path) -> None:
        """The rule enforces catch-order across the full web/ subtree so a
        sibling module (e.g. a future web/composer helper) cannot silently
        re-introduce the laundering pattern the route was fixed for."""
        # Canonical target must exist so the fail-closed guard passes…
        _make_routes_tree(tmp_path, "pass\n")
        # …and the violation lives in a different file under web/.
        sibling = tmp_path / "web" / "composer"
        sibling.mkdir(parents=True)
        (sibling / "helper.py").write_text(
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except ComposerServiceError as exc:\n"
            "        pass\n"
            "    except ComposerPluginCrashError as crash:\n"
            "        pass\n",
        )
        result = _run(["check", "--root", str(tmp_path)])
        assert result.returncode != 0
        assert "web/composer/helper.py" in result.stdout

    def test_tuple_handler_is_flagged(self, tmp_path: Path) -> None:
        """An earlier handler that tuple-catches the supertype also shadows
        the subclass. The AST walker unpacks ``except (A, B):`` tuples."""
        _make_routes_tree(
            tmp_path,
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except (RuntimeError, ComposerServiceError) as exc:\n"
            "        pass\n"
            "    except ComposerPluginCrashError as crash:\n"
            "        pass\n",
        )
        result = _run(["check", "--root", str(tmp_path)])
        assert result.returncode != 0

    def test_attribute_handler_is_flagged(self, tmp_path: Path) -> None:
        """Module-qualified references (``except protocol.ComposerServiceError``)
        must still be detected — the AST walker reads the last attribute
        segment, matching how Python resolves the class at runtime."""
        _make_routes_tree(
            tmp_path,
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except protocol.ComposerServiceError as exc:\n"
            "        pass\n"
            "    except ComposerPluginCrashError as crash:\n"
            "        pass\n",
        )
        result = _run(["check", "--root", str(tmp_path)])
        assert result.returncode != 0

    def test_only_subclass_caught_passes(self, tmp_path: Path) -> None:
        """A try block that catches only the subclass (no supertype present)
        is unaffected by the rule."""
        _make_routes_tree(
            tmp_path,
            "def f():\n    try:\n        pass\n    except ComposerPluginCrashError as crash:\n        pass\n",
        )
        result = _run(["check", "--root", str(tmp_path)])
        assert result.returncode == 0, result.stdout + result.stderr

    def test_only_supertype_caught_passes(self, tmp_path: Path) -> None:
        """A try block that catches only the supertype (no subclass present)
        is unaffected — there is no shadowed handler."""
        _make_routes_tree(
            tmp_path,
            "def f():\n    try:\n        pass\n    except ComposerServiceError as exc:\n        pass\n",
        )
        result = _run(["check", "--root", str(tmp_path)])
        assert result.returncode == 0, result.stdout + result.stderr

    def test_unrelated_exception_pair_passes(self, tmp_path: Path) -> None:
        """A try block with except handlers for classes outside the declared
        hierarchy does not trigger CCO1."""
        _make_routes_tree(
            tmp_path,
            "def f():\n    try:\n        pass\n    except OSError:\n        pass\n    except ValueError:\n        pass\n",
        )
        result = _run(["check", "--root", str(tmp_path)])
        assert result.returncode == 0, result.stdout + result.stderr

    def test_missing_canonical_target_fails_closed(self, tmp_path: Path) -> None:
        """If web/sessions/routes.py is missing under the root, exit non-zero.

        A future rename of routes.py would otherwise cause the enforcer to
        silently scan a tree without the invariant's canonical home.
        """
        # No _make_routes_tree() call — target is absent.
        result = _run(["check", "--root", str(tmp_path)])
        assert result.returncode != 0
        assert "web/sessions/routes.py" in (result.stdout + result.stderr)

    def test_allowlist_entry_suppresses_matching_finding(self, tmp_path: Path) -> None:
        """An allowlist entry at the exact (file, line) of the shadowed
        subclass handler suppresses the finding and the enforcer exits 0."""
        _make_routes_tree(
            tmp_path,
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except ComposerServiceError as exc:\n"
            "        pass\n"
            "    except ComposerPluginCrashError as crash:\n"
            "        pass\n",
        )
        # The CCO1 finding is anchored to the shadowed (subclass) handler.
        # In the body above, that handler is on line 6.
        allowlist_dir = tmp_path / "allowlist"
        allowlist_dir.mkdir()
        (allowlist_dir / "_defaults.yaml").write_text(
            'allowed:\n  - file: web/sessions/routes.py\n    line: 6\n    justification: "test-only exemption; real code never uses this"\n'
        )
        result = _run(
            [
                "check",
                "--root",
                str(tmp_path),
                "--allowlist",
                str(allowlist_dir),
            ]
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_allowlist_entry_with_empty_justification_fails(self, tmp_path: Path) -> None:
        _make_routes_tree(
            tmp_path,
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except ComposerServiceError as exc:\n"
            "        pass\n"
            "    except ComposerPluginCrashError as crash:\n"
            "        pass\n",
        )
        allowlist_dir = tmp_path / "allowlist"
        allowlist_dir.mkdir()
        (allowlist_dir / "_defaults.yaml").write_text('allowed:\n  - file: web/sessions/routes.py\n    line: 6\n    justification: ""\n')
        result = _run(
            [
                "check",
                "--root",
                str(tmp_path),
                "--allowlist",
                str(allowlist_dir),
            ]
        )
        assert result.returncode != 0
        assert "justification" in (result.stdout + result.stderr)

    def test_allowlist_entry_missing_justification_key_fails(self, tmp_path: Path) -> None:
        _make_routes_tree(
            tmp_path,
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except ComposerServiceError as exc:\n"
            "        pass\n"
            "    except ComposerPluginCrashError as crash:\n"
            "        pass\n",
        )
        allowlist_dir = tmp_path / "allowlist"
        allowlist_dir.mkdir()
        (allowlist_dir / "_defaults.yaml").write_text("allowed:\n  - file: web/sessions/routes.py\n    line: 6\n")
        result = _run(
            [
                "check",
                "--root",
                str(tmp_path),
                "--allowlist",
                str(allowlist_dir),
            ]
        )
        assert result.returncode != 0
        assert "justification" in (result.stdout + result.stderr)

    def test_allowlist_entry_missing_file_key_fails(self, tmp_path: Path) -> None:
        _make_routes_tree(
            tmp_path,
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except ComposerServiceError as exc:\n"
            "        pass\n"
            "    except ComposerPluginCrashError as crash:\n"
            "        pass\n",
        )
        allowlist_dir = tmp_path / "allowlist"
        allowlist_dir.mkdir()
        (allowlist_dir / "_defaults.yaml").write_text("allowed:\n  - line: 6\n    justification: 'missing file key'\n")
        result = _run(["check", "--root", str(tmp_path), "--allowlist", str(allowlist_dir)])
        assert result.returncode != 0
        assert "file" in (result.stdout + result.stderr).lower()

    def test_allowlist_entry_missing_line_key_fails(self, tmp_path: Path) -> None:
        _make_routes_tree(
            tmp_path,
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except ComposerServiceError as exc:\n"
            "        pass\n"
            "    except ComposerPluginCrashError as crash:\n"
            "        pass\n",
        )
        allowlist_dir = tmp_path / "allowlist"
        allowlist_dir.mkdir()
        (allowlist_dir / "_defaults.yaml").write_text("allowed:\n  - file: web/sessions/routes.py\n    justification: 'missing line key'\n")
        result = _run(["check", "--root", str(tmp_path), "--allowlist", str(allowlist_dir)])
        assert result.returncode != 0
        assert "line" in (result.stdout + result.stderr).lower()

    def test_allowlist_entry_non_integer_line_fails(self, tmp_path: Path) -> None:
        _make_routes_tree(
            tmp_path,
            "def f():\n"
            "    try:\n"
            "        pass\n"
            "    except ComposerServiceError as exc:\n"
            "        pass\n"
            "    except ComposerPluginCrashError as crash:\n"
            "        pass\n",
        )
        allowlist_dir = tmp_path / "allowlist"
        allowlist_dir.mkdir()
        (allowlist_dir / "_defaults.yaml").write_text(
            "allowed:\n  - file: web/sessions/routes.py\n    line: 'not-a-number'\n    justification: 'bad line'\n"
        )
        result = _run(["check", "--root", str(tmp_path), "--allowlist", str(allowlist_dir)])
        assert result.returncode != 0
        assert "line" in (result.stdout + result.stderr).lower()

    def test_allowlist_path_not_found_fails_closed(self, tmp_path: Path) -> None:
        _make_routes_tree(tmp_path, "pass\n")
        bogus = tmp_path / "does-not-exist"
        result = _run(["check", "--root", str(tmp_path), "--allowlist", str(bogus)])
        assert result.returncode != 0
        assert "does not exist" in (result.stdout + result.stderr).lower()

    def test_real_routes_pass_production_check(self) -> None:
        """The live src/elspeth tree must pass — otherwise we shipped a
        regression. This pins the invariant at CI time and also guards
        against a bug in the enforcer itself that would false-positive."""
        project_root = Path(__file__).resolve().parents[4]
        result = _run(
            [
                "check",
                "--root",
                str(project_root / "src" / "elspeth"),
                "--allowlist",
                str(project_root / "config" / "cicd" / "enforce_composer_catch_order"),
            ]
        )
        assert result.returncode == 0, result.stdout + result.stderr


class TestHierarchyConsistency:
    """Cross-check the hard-coded subclass map against the real MRO.

    The enforcer stores the composer-exception hierarchy as a hard-coded
    dict because we want fast AST-only scanning without importing runtime
    code during CI. The trade-off is drift risk: a new
    ``ComposerServiceError`` subclass added to
    ``elspeth.web.composer.protocol`` would bypass the gate entirely. This
    test imports the real classes and asserts the dict agrees with Python's
    ``__mro__`` view so drift fails CI loudly, forcing the enforcer update.
    """

    def test_declared_map_matches_real_mro(self) -> None:
        from scripts.cicd.enforce_composer_catch_order import _SUBCLASS_TO_SUPERCLASSES

        from elspeth.web.composer.protocol import ComposerServiceError

        real_subclasses = {cls.__name__ for cls in ComposerServiceError.__subclasses__()}
        declared_subclasses = set(_SUBCLASS_TO_SUPERCLASSES.keys())
        assert real_subclasses == declared_subclasses, (
            "enforce_composer_catch_order._SUBCLASS_TO_SUPERCLASSES is out of "
            f"sync with the real ComposerServiceError hierarchy. Real: "
            f"{sorted(real_subclasses)} Declared: {sorted(declared_subclasses)}. "
            "Update the dict in scripts/cicd/enforce_composer_catch_order.py "
            "so the new subclass is enforced."
        )

    def test_declared_supertypes_include_composer_service_error(self) -> None:
        """Every declared subclass must list ``ComposerServiceError`` as a
        supertype — that's the hierarchy this gate exists to protect."""
        from scripts.cicd.enforce_composer_catch_order import _SUBCLASS_TO_SUPERCLASSES

        for sub, supers in _SUBCLASS_TO_SUPERCLASSES.items():
            assert "ComposerServiceError" in supers, (
                f"{sub} entry missing ComposerServiceError supertype; the "
                "gate would not detect a ComposerServiceError handler "
                f"shadowing a {sub} handler."
            )
