from __future__ import annotations

import tarfile

from elspeth.plugins.nodes.sinks.reproducibility_bundle import ReproducibilityBundleSink


def test_filter_framework_files_excludes_pycache_and_tests():
    # Build TarInfo entries with representative names
    keep = tarfile.TarInfo(name="elspeth/core/module.py")
    drop_pyc = tarfile.TarInfo(name="elspeth/__pycache__/module.cpython-312.pyc")
    drop_test = tarfile.TarInfo(name="elspeth/tests/test_mod.py")

    assert ReproducibilityBundleSink._filter_framework_files(keep) is keep
    assert ReproducibilityBundleSink._filter_framework_files(drop_pyc) is None
    assert ReproducibilityBundleSink._filter_framework_files(drop_test) is None

