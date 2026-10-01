from __future__ import annotations
import importlib.util
import unittest
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DPStdBudgetTests(unittest.TestCase):
    def load(self, folder):
        path = ROOT / "generation/baselines" / folder / "DPStd/dpstd_final.py"
        spec = importlib.util.spec_from_file_location("dpstd_budget_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_total_budget_reaches_both_noise_blocks(self):
        for folder in ("src/reproduced_papers", "algorithms/literature_baselines/source_snapshot"):
            module = self.load(folder)
            for epsilon in (0.2, 1, 1.4, 3):
                with self.subTest(folder=folder, epsilon=epsilon):
                    model = module.DPStdModel(epsilon, bbox_dict={})
                    self.assertAlmostEqual(model.epsilon1, 0.1 * epsilon)
                    self.assertAlmostEqual(model.epsilon2, 0.9 * epsilon)
                    self.assertAlmostEqual(model.epsilon1 + model.epsilon2, epsilon)

    def test_explicit_allocation_preserved(self):
        module = self.load("src/reproduced_papers")
        model = module.DPStdModel(1.4, epsilon1=0, epsilon2=1.4, bbox_dict={})
        self.assertEqual((model.epsilon1, model.epsilon2), (0, 1.4))

    def test_fitted_budget_ledger_matches_requested_budget(self):
        module = self.load("src/reproduced_papers")
        bbox = {"lat_min": 39.75, "lat_max": 40.15, "lon_min": 116.10, "lon_max": 116.65}
        trajectories = [np.array([[39.9, 116.3], [39.901, 116.302], [39.902, 116.304]]) for _ in range(6)]
        for epsilon in (0.7, 1.4):
            np.random.seed(42)
            model = module.DPStdModel(epsilon, bbox_dict=bbox)
            model.fit(trajectories)
            self.assertAlmostEqual(model._eps_grid_consumed, 0.1 * epsilon)
            self.assertAlmostEqual(model._eps_stats_consumed, 0.9 * epsilon)
            self.assertAlmostEqual(model._eps_total_consumed, epsilon)
