"""Baseline wrappers must reject missing required solvers before creating output."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "generation/baselines/algorithms/literature_baselines/entrypoints/generate.py"
SPEC = importlib.util.spec_from_file_location("baseline_generate_preflight", ENTRY)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BaselineDependencyPreflightTest(unittest.TestCase):
    def test_relative_custom_input_forwarded_as_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT, prefix="path fixture ") as directory:
            folder = Path(directory)
            source = folder / "input.pkl"
            osm = folder / "osm.pkl"
            source.write_bytes(b"fixture")
            osm.write_bytes(b"fixture")
            argv = ["generate.py", "--method", "sprt-native", "--data", str(source.relative_to(ROOT)),
                    "--epsilon", "1.4", "--out-dir", str((folder / "out").relative_to(ROOT)),
                    "--bbox", "39.75", "40.15", "116.10", "116.65", "--osm-cache", str(osm),
                    "--public-slot-count", "2"]
            with patch.object(sys, "argv", argv), patch.object(MODULE.importlib.util, "find_spec", return_value=object()):
                with patch.object(MODULE.subprocess, "run") as process:
                    process.return_value.returncode = 0
                    MODULE.main()
                    command = process.call_args.args[0]
                    self.assertEqual(command[command.index("--data") + 1], str(source.resolve()))

    def test_extra_arguments_cannot_replace_bound_inputs_or_budget(self) -> None:
        for token in ("--epsilon=100", "--data=another.pkl", "--n-gen=1", "--seed=9"):
            argv = ["generate.py", "--method", "sprt-native", "--data", "unused.pkl",
                    "--epsilon", "1.4", "--out-dir", "unused-output", f"--extra-arg={token}"]
            with self.subTest(token=token), patch.object(sys, "argv", argv):
                with self.assertRaisesRegex(ValueError, "cannot override"):
                    MODULE.main()

    def test_nonfinite_budget_rejected_before_output(self) -> None:
        argv = ["generate.py", "--method", "sprt-native", "--data", "unused.pkl",
                "--epsilon", "nan", "--out-dir", "unused-output"]
        with patch.object(sys, "argv", argv):
            with patch.object(MODULE, "require_new_directory", side_effect=AssertionError("created output too early")):
                with self.assertRaisesRegex(ValueError, "finite positive"):
                    MODULE.main()

    def check_missing(self, method: str, missing: str) -> None:
        argv = ["generate.py", "--method", method, "--data", "unused.pkl",
                "--epsilon", "1", "--out-dir", "unused-output"]
        def find_spec(name: str):
            # Isolate the dependency under test from the host environment.
            return None if name == missing else object()

        with patch.object(sys, "argv", argv), patch.object(MODULE.importlib.util, "find_spec", side_effect=find_spec):
            with patch.object(MODULE, "require_new_directory", side_effect=AssertionError("created output too early")):
                with self.assertRaisesRegex(RuntimeError, missing):
                    MODULE.main()

    def test_requests_preflight(self) -> None:
        self.check_missing("sprt-native", "requests")

    def test_privtrace_solver_preflight(self) -> None:
        self.check_missing("privtrace-native", "cvxpy")

    def test_custom_data_requires_public_graph_configuration(self) -> None:
        argv = ["generate.py", "--method", "sprt-native", "--data", "custom.pkl",
                "--epsilon", "1", "--out-dir", "unused-output"]
        with patch.object(sys, "argv", argv), patch.object(MODULE.importlib.util, "find_spec", return_value=object()):
            with patch.object(MODULE, "require_new_directory", side_effect=AssertionError("created output too early")):
                with self.assertRaisesRegex(RuntimeError, "custom data requires --bbox"):
                    MODULE.main()


if __name__ == "__main__":
    unittest.main()
