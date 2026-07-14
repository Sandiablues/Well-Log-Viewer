import ast
import inspect
import textwrap

from app.inventory.service import ManagedWellInventoryService


def _call_lines():
    source = textwrap.dedent(
        inspect.getsource(ManagedWellInventoryService.bulk_load_wdv_workspace)
    )
    tree = ast.parse(source)
    result = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            name = ".".join(reversed(parts))
            result.setdefault(name, []).append(node.lineno)
    return result


def test_session_is_built_before_snapshot_write():
    calls = _call_lines()
    sync_line = calls["self._sync_wdv_load_session_for_record"][0]
    write_line = calls["self.repository.write_snapshot"][0]
    assert sync_line < write_line


def test_snapshot_is_written_before_workspace_reconcile():
    calls = _call_lines()
    write_line = calls["self.repository.write_snapshot"][0]
    reconcile_line = calls["self.workspace_service.reconcile"][0]
    assert write_line < reconcile_line
