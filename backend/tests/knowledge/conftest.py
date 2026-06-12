"""Knowledge test suite shared fixtures and isolation.

KR-5 storage isolation
----------------------
``ManagedKRRepository()`` (no args) now defaults to
``backend/data/knowledge/managed_knowledge.json``.  Without isolation,
any KR-2/3/4 test that calls ``repo.promote_to_approved()``,
``repo.deprecate_record()``, or imports via ``stage_import_payload()``
would WRITE to the real project storage file.

This autouse fixture patches ``DEFAULT_STORAGE_PATH`` in the
``managed_storage`` module to a per-test temp path BEFORE any test
fixture that calls ``ManagedKRRepository()`` runs.  Pytest executes
autouse fixtures at each scope level before non-autouse fixtures at
the same scope, so the patch is guaranteed to be in effect when the
test-file ``repo`` fixtures construct their repositories.

Tests that explicitly pass ``storage_path=`` to ``ManagedKRRepository``
(e.g. in ``test_kr5_persistent_storage.py``) are unaffected because
the constructor's explicit argument takes precedence over the module
default.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import backend.app.knowledge.managed_storage as _storage_module


@pytest.fixture(autouse=True)
def _isolate_managed_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the default storage path to a per-test temp directory.

    Applies to every test in the knowledge suite.  Tests in
    test_kr5_persistent_storage.py that supply an explicit storage_path
    are unaffected — the constructor ignores the module default when a
    path is provided.
    """
    test_storage_path = tmp_path / "_default_managed_knowledge.json"
    monkeypatch.setattr(_storage_module, "DEFAULT_STORAGE_PATH", test_storage_path)
