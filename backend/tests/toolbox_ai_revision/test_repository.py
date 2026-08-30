from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.toolbox_ai_revision.repository import ToolboxAiRevisionRepository


class ToolboxAiRevisionRepositoryTests(unittest.TestCase):
    def test_persistence_independence_sync_and_correction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            repo = ToolboxAiRevisionRepository(path)

            self.assertIsNone(repo.get("FTM", "well-a"))
            self.assertEqual(repo.allocate("FTM", "well-a")["current_revision"], 1)
            self.assertEqual(repo.allocate("FTM", "well-a")["current_revision"], 2)
            self.assertEqual(repo.allocate("CDM", "well-a")["current_revision"], 1)
            self.assertEqual(repo.allocate("FTM", "well-b")["current_revision"], 1)

            reloaded = ToolboxAiRevisionRepository(path)
            self.assertEqual(reloaded.get("FTM", "well-a")["current_revision"], 2)
            self.assertEqual(reloaded.synchronize("FTM", "well-a", 1)["current_revision"], 2)
            self.assertEqual(
                reloaded.synchronize("FTM", "well-a", 4, reason="response import")["current_revision"],
                4,
            )

            corrected = reloaded.correct(
                "FTM",
                "well-a",
                3,
                reason="operator correction",
                actor="test",
            )
            self.assertEqual(corrected["current_revision"], 3)
            self.assertEqual(corrected["history"][-1]["action"], "explicit_correction")
            self.assertEqual(corrected["history"][-1]["previous_revision"], 4)

    def test_atomic_allocation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = ToolboxAiRevisionRepository(Path(tmp) / "registry.json")

            def allocate(_: int) -> int:
                return repo.allocate("CIM_JOIN", "well-x")["current_revision"]

            with ThreadPoolExecutor(max_workers=8) as pool:
                revisions = list(pool.map(allocate, range(20)))

            self.assertEqual(sorted(revisions), list(range(1, 21)))
            self.assertEqual(repo.get("CIM_JOIN", "well-x")["current_revision"], 20)


if __name__ == "__main__":
    unittest.main()
