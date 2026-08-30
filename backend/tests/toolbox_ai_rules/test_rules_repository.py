from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.toolbox_ai_revision.rules_repository import ToolboxAiRulesRepository


class ToolboxAiRulesRepositoryTests(unittest.TestCase):
    def test_query_save_previous_restore_and_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rules.json"
            repo = ToolboxAiRulesRepository(path)
            original = repo.get("FTM")
            self.assertIn("instructions", original["rules"])

            changed = repo.save("FTM", {"purpose": "test", "instructions": ["one"]}, "unit-test")
            self.assertEqual(changed["rules"]["instructions"], ["one"])
            self.assertEqual(changed["previous_rules"], original["rules"])

            reloaded = ToolboxAiRulesRepository(path)
            self.assertEqual(reloaded.get("FTM")["rules"]["instructions"], ["one"])

            restored = reloaded.restore_previous("FTM")
            self.assertEqual(restored["rules"], original["rules"])

            reset = reloaded.reset_default("FTM")
            self.assertIn("instructions", reset["rules"])

    def test_tool_rules_are_independent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = ToolboxAiRulesRepository(Path(tmp) / "rules.json")
            repo.save("CDM", {"instructions": ["cdm-only"]})
            self.assertEqual(repo.get("CDM")["rules"]["instructions"], ["cdm-only"])
            self.assertNotEqual(repo.get("FTM")["rules"]["instructions"], ["cdm-only"])


if __name__ == "__main__":
    unittest.main()
