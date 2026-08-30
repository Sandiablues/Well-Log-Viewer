from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.toolbox_ai_revision.standards_repository import ToolboxAiStandardsRepository


class ToolboxAiStandardsRepositoryTests(unittest.TestCase):
    def test_default_versioning_and_restore_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "standards.json"
            legacy = Path(tmp) / "legacy.json"
            repo = ToolboxAiStandardsRepository(path, legacy)

            first = repo.get_active("FTM")
            self.assertEqual(first["active_version"], 1)

            second = repo.save_new_version(
                "FTM",
                {"purpose": "changed", "instructions": ["v2"]},
                created_by="unit-test",
                change_note="Change rule",
            )
            self.assertEqual(second["active_version"], 2)
            self.assertEqual(repo.get_version("FTM", 1)["rules"], first["rules"])
            self.assertEqual(repo.get_version("FTM", 2)["rules"]["instructions"], ["v2"])

            restored = repo.restore_as_new_version("FTM", 1, created_by="unit-test")
            self.assertEqual(restored["active_version"], 3)
            self.assertEqual(repo.get_version("FTM", 3)["rules"], first["rules"])
            self.assertEqual(repo.get_version("FTM", 2)["rules"]["instructions"], ["v2"])

    def test_legacy_active_rules_migrate_as_version_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "standards.json"
            legacy = Path(tmp) / "toolbox_ai_rules_v1.json"
            legacy.write_text(json.dumps({
                "schema_version": "toolbox_ai_rules_v1",
                "tools": {
                    "FTM": {
                        "tool": "FTM",
                        "rules": {"instructions": ["current-live-rule"]},
                        "previous_rules": {"instructions": ["old-rule"]},
                        "updated_at": "2026-08-24T10:42:00+01:00",
                        "updated_by": "operator"
                    }
                }
            }))
            repo = ToolboxAiStandardsRepository(path, legacy)
            active = repo.get_active("FTM")
            self.assertEqual(active["active_version"], 1)
            self.assertEqual(active["rules"]["instructions"], ["current-live-rule"])
            v1 = repo.get_version("FTM", 1)
            self.assertEqual(v1["migrated_previous_rules"]["instructions"], ["old-rule"])

    def test_tools_version_independently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = ToolboxAiStandardsRepository(
                Path(tmp) / "standards.json",
                Path(tmp) / "legacy.json",
            )
            repo.save_new_version("CDM", {"instructions": ["cdm-v2"]})
            self.assertEqual(repo.get_active("CDM")["active_version"], 2)
            self.assertEqual(repo.get_active("FTM")["active_version"], 1)


    def test_delete_version_rejects_active_and_referenced_versions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "standards.json"
            repo = ToolboxAiStandardsRepository(path, root / "legacy.json")

            repo.save_new_version("FTM", {"instructions": ["v2"]})
            repo.save_new_version("FTM", {"instructions": ["v3"]})

            with self.assertRaisesRegex(ValueError, "active"):
                repo.delete_version("FTM", 3)

            audit = root / "qualification_run.json"
            audit.write_text(json.dumps({
                "schema_version": "test",
                "tool": "FTM",
                "standard_version": 1,
            }))
            with self.assertRaisesRegex(ValueError, "referenced"):
                repo.delete_version("FTM", 1)

            result = repo.delete_version("FTM", 2)
            self.assertEqual(result["active_version"], 3)
            self.assertEqual([item["version"] for item in result["versions"]], [1, 3])
            self.assertEqual(repo.get_version("FTM", 3)["rules"]["instructions"], ["v3"])
            with self.assertRaisesRegex(ValueError, "does not exist"):
                repo.get_version("FTM", 2)



if __name__ == "__main__":
    unittest.main()
