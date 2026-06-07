"""
Tests — LAS Import Service
WL-BUILD-001 scaffold

These tests validate:
- Module importability
- Service class existence and interface shape
- That NotImplementedError is raised (scaffold state)
- That frontend LAS parsing is not present in the service
"""

import pytest

from backend.app.wells.las_import_service import LasImportError, LasImportService
from backend.app.wells.models import MsiSourceRef


class TestLasImportServiceScaffold:
    """Scaffold-state tests — verifies structure, not implementation."""

    def test_module_importable(self):
        """The las_import_service module must be importable."""
        from backend.app.wells import las_import_service  # noqa: F401

    def test_service_class_exists(self):
        svc = LasImportService()
        assert svc is not None

    def test_import_from_path_raises_not_implemented(self):
        """
        WL-BUILD-001: import_from_path must raise NotImplementedError.
        Full implementation deferred to later sprint.
        """
        svc = LasImportService()
        source_ref = MsiSourceRef(source_id="src-001", filename="test.las")
        with pytest.raises(NotImplementedError):
            svc.import_from_path("/tmp/test.las", source_ref)

    def test_import_from_bytes_raises_not_implemented(self):
        svc = LasImportService()
        source_ref = MsiSourceRef(source_id="src-001")
        with pytest.raises(NotImplementedError):
            svc.import_from_bytes(b"", source_ref)

    def test_las_import_error_is_exception(self):
        """LasImportError must be an Exception subclass."""
        assert issubclass(LasImportError, Exception)

    def test_no_las_parsing_in_module(self):
        """
        Verify that no LAS parsing library (lasio, welly, etc.) is imported
        at the module level in WL-BUILD-001.
        Parsing libraries will be added in a later sprint via explicit dependency setup.
        """
        import ast
        import pathlib

        source = pathlib.Path("backend/app/wells/las_import_service.py").read_text()
        tree = ast.parse(source)
        top_level_imports = [
            node for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ]
        prohibited_modules = {"lasio", "welly", "striplog"}
        for node in top_level_imports:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in prohibited_modules, (
                        f"Prohibited LAS parsing import found: {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    assert node.module.split(".")[0] not in prohibited_modules, (
                        f"Prohibited LAS parsing import found: {node.module}"
                    )
