import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch
import json

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from algorithms.native.dpmm_adapter import build_accelerated_command, run_accelerated


class DPMMAdapterTests(unittest.TestCase):
    def test_accelerated_command_contains_validation_and_workers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {}
            for name in ("run_dpmm_fast.py", "adapter.py", "validation.json", "input.pkl", "osm.pkl"):
                path = root / name
                path.write_bytes(b"placeholder")
                files[name] = path
            command = build_accelerated_command(
                accelerator_script=files["run_dpmm_fast.py"],
                adapter=files["adapter.py"],
                validation=files["validation.json"],
                input_pkl=files["input.pkl"],
                osm_cache=files["osm.pkl"],
                bbox=(39.75, 40.15, 116.10, 116.65),
                epsilon=1.4,
                seed=20260714,
                zone_radius_m=25,
                utm_zone_number=50,
                utm_zone_letter="S",
                clean_seed_waypoint_mode="rdp",
                workers=16,
                checkpoint_every=25,
                out_dir=root / "out",
                tag="dpmm_fast16_eps14",
                resume=True,
            )
            self.assertIn("--validation", command)
            self.assertIn("--workers", command)
            self.assertEqual(command[command.index("--workers") + 1], "16")
            self.assertIn("--resume", command)

    def test_accelerated_run_rejects_incomplete_output_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {}
            for name in ("run_dpmm_fast.py", "adapter.py", "validation.json", "input.pkl", "osm.pkl"):
                path = root / name
                path.write_bytes(b"placeholder")
                files[name] = path
            out = root / "out"

            def fake_run(command, cwd, check):
                out.mkdir(parents=True, exist_ok=True)
                (out / "tag.pkl").write_bytes(b"release")
                (out / "tag.json").write_text(json.dumps({"output_count": 3}), encoding="utf-8")

            with patch("algorithms.native.dpmm_adapter.subprocess.run", side_effect=fake_run):
                with self.assertRaisesRegex(ValueError, "output_count=3.*public_slot_count=4"):
                    run_accelerated(
                        accelerator_script=files["run_dpmm_fast.py"],
                        adapter=files["adapter.py"],
                        validation=files["validation.json"],
                        input_pkl=files["input.pkl"],
                        osm_cache=files["osm.pkl"],
                        bbox=(39.75, 40.15, 116.10, 116.65),
                        epsilon=1.4,
                        seed=20260714,
                        zone_radius_m=25,
                        utm_zone_number=50,
                        utm_zone_letter="S",
                        clean_seed_waypoint_mode="rdp",
                        workers=2,
                        checkpoint_every=1,
                        expected_output_count=4,
                        allow_partial_output=False,
                        out_dir=out,
                        tag="tag",
                        resume=False,
                    )

    def test_accelerated_run_records_partial_output_only_when_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {}
            for name in ("run_dpmm_fast.py", "adapter.py", "validation.json", "input.pkl", "osm.pkl"):
                path = root / name
                path.write_bytes(b"placeholder")
                files[name] = path
            out = root / "out"

            def fake_run(command, cwd, check):
                out.mkdir(parents=True, exist_ok=True)
                (out / "tag.pkl").write_bytes(b"release")
                (out / "tag.json").write_text(json.dumps({"output_count": 3}), encoding="utf-8")

            with patch("algorithms.native.dpmm_adapter.subprocess.run", side_effect=fake_run):
                record = run_accelerated(
                    accelerator_script=files["run_dpmm_fast.py"],
                    adapter=files["adapter.py"],
                    validation=files["validation.json"],
                    input_pkl=files["input.pkl"],
                    osm_cache=files["osm.pkl"],
                    bbox=(39.75, 40.15, 116.10, 116.65),
                    epsilon=1.4,
                    seed=20260714,
                    zone_radius_m=25,
                    utm_zone_number=50,
                    utm_zone_letter="S",
                    clean_seed_waypoint_mode="rdp",
                    workers=2,
                    checkpoint_every=1,
                    expected_output_count=4,
                    allow_partial_output=True,
                    out_dir=out,
                    tag="tag",
                    resume=False,
                )
            self.assertEqual(record["status"], "VALID_PARTIAL")
            self.assertEqual(record["actual_output_count"], 3)
            self.assertAlmostEqual(record["output_yield"], 0.75)


if __name__ == "__main__":
    unittest.main()
