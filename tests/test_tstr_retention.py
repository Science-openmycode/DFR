from __future__ import annotations

import unittest
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "evaluation" / "run_tstr_experiment.py"
SPEC = importlib.util.spec_from_file_location("run_tstr_experiment", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
retained = MODULE.retained


class TstrRetentionTest(unittest.TestCase):
    def test_coverage_is_part_of_task_utility(self) -> None:
        real = {"coverage": "1", "quality": "0.8"}
        self.assertEqual(retained(real, real, "coverage", "quality"), 1.0)
        self.assertEqual(retained({"coverage": "0.5", "quality": "0.8"}, real,
                                  "coverage", "quality"), 0.5)
        self.assertEqual(retained({"coverage": "0", "quality": "1"}, real,
                                  "coverage", "quality"), 0.0)


if __name__ == "__main__":
    unittest.main()
