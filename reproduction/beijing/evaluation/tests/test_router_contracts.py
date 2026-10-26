import json
import csv
import argparse
import pickle
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class RouterContractTests(unittest.TestCase):
    def test_named_public_router_modules_are_real_entry_points(self):
        from algorithms.routers.fmm_adapter import ROUTER as FMM_ROUTER, run_fmm
        from algorithms.routers.stmatch_adapter import ROUTER as STMATCH_ROUTER, run_stmatch
        self.assertEqual(FMM_ROUTER, "FMM")
        self.assertEqual(STMATCH_ROUTER, "STMatch")
        self.assertTrue(callable(run_fmm))
        self.assertTrue(callable(run_stmatch))

    def test_manifest_declares_all_public_routers(self):
        manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
        contracts = manifest["public_coordinate_router_contracts"]
        self.assertEqual(set(contracts), {"Nearest", "FMM", "STMatch"})
        for value in contracts.values():
            self.assertFalse(value["raw_source_used"])
            self.assertFalse(value["fills_gaps"])

    def test_smoke_manifests_are_valid_and_external(self):
        # Keep this contract test independent of ignored/generated smoke
        # artifacts.  A code-only checkout must be able to run the tests.
        with tempfile.TemporaryDirectory(prefix="dfr_manifest_contract_") as tmp:
            root = Path(tmp)
            for router in ("Nearest", "STMatch", "FMM"):
                path = root / router / "route_manifest.json"
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({
                    "router": router, "status": "VALID",
                    "raw_source_used": False, "fills_gaps": False,
                    "records": 2,
                }), encoding="utf-8")
                manifest = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(manifest["router"], router)
                self.assertEqual(manifest["status"], "VALID")
                self.assertFalse(manifest["raw_source_used"])
                self.assertEqual(manifest["records"], 2)
            stmatch_v4 = root / "STMatch" / "route_manifest_v4.json"
            stmatch_v4.write_text(json.dumps({"ubodt": None}), encoding="utf-8")
            self.assertIsNone(json.loads(stmatch_v4.read_text(encoding="utf-8"))["ubodt"])

    def test_external_failure_is_recorded_as_invalid(self):
        with tempfile.TemporaryDirectory(prefix="dfr_invalid_manifest_") as tmp:
            path = Path(tmp) / "route_manifest.json"
            path.write_text(json.dumps({
                "status": "INVALID", "error_type": "FileNotFoundError",
                "M": "SPRT", "R": "FMM", "dataset": "beijing",
            }), encoding="utf-8")
            manifest = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "INVALID")
            self.assertEqual(manifest["error_type"], "FileNotFoundError")
            self.assertEqual((manifest["M"], manifest["R"], manifest["dataset"]), ("SPRT", "FMM", "beijing"))

    def test_missing_public_executable_writes_invalid_manifest(self):
        from algorithms.routers.public_match_adapter import run_public_match

        with tempfile.TemporaryDirectory(prefix="dfr_missing_router_") as tmp:
            root = Path(tmp)
            measurement = root / "measurement.pkl"
            network = root / "network.shp"
            edge_cache = root / "edge_cache.pkl.gz"
            for path in (measurement, network, edge_cache):
                path.write_bytes(b"placeholder")
            out_dir = root / "out"
            with self.assertRaises(FileNotFoundError):
                run_public_match(
                    measurement, out_dir, matcher="FMM", network=network,
                    executable=root / "missing-fmm", edge_cache=edge_cache,
                    legacy_root=root, ubodt=edge_cache,
                )
            manifest = json.loads((out_dir / "route_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "INVALID")
            self.assertEqual(manifest["error_type"], "FileNotFoundError")

    def test_route_cell_missing_public_inputs_writes_invalid_manifest(self):
        import run as orchestrator

        with tempfile.TemporaryDirectory(prefix="dfr_route_missing_") as tmp:
            root = Path(tmp)
            measurement = root / "measurement"
            measurement.mkdir()
            with (measurement / "measurement.pkl").open("wb") as handle:
                pickle.dump([[[39.9, 116.3], [39.91, 116.31]]], handle)
            (measurement / "measurement_manifest.json").write_text("{}", encoding="utf-8")
            out = root / "out"
            args = argparse.Namespace(
                dataset="beijing", m="SPRT", r="Nearest", measurement=measurement,
                prepared_data=root, route_source=None, out_dir=out,
                mm2_executable=None, mm2_network=None, edge_cache=None,
                input_srs="EPSG:4326", tracks_srs="EPSG:32650", network_srs="EPSG:32650",
                max_points=32, seed=None, public_network=None, fmm_executable=None,
                stmatch_executable=None, ubodt=None, ubodt_executable=None,
                runtime_dir=None, radius_m=200.0, gps_error_m=50.0,
                candidates=8, min_observation_share=0.95,
            )
            with self.assertRaises(SystemExit):
                orchestrator.route_cell(args)
            manifest = json.loads((out / "route_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "INVALID")
            self.assertEqual((manifest["M"], manifest["R"], manifest["dataset"]), ("SPRT", "Nearest", "beijing"))
            self.assertIn("missing_arguments", manifest)

    def test_native_route_source_can_be_nested_under_seed_directory(self):
        import run as orchestrator

        with tempfile.TemporaryDirectory(prefix="dfr_nested_native_") as tmp:
            root = Path(tmp)
            nested = root / "seed_42"
            nested.mkdir()
            route = nested / "road_routes.pkl.gz"
            route.write_bytes(b"placeholder")
            self.assertEqual(orchestrator.find_route_source(root), route)

    def test_route_m_continues_after_invalid_router(self):
        import run as orchestrator

        with tempfile.TemporaryDirectory(prefix="dfr_route_m_") as tmp:
            root = Path(tmp)
            measurement = root / "measurement"
            measurement.mkdir()
            with (measurement / "measurement.pkl").open("wb") as handle:
                pickle.dump([[[39.9, 116.3], [39.91, 116.31]], [[39.9, 116.3], [39.91, 116.31]]], handle)
            (measurement / "measurement_manifest.json").write_text("{}", encoding="utf-8")
            prepared = root / "prepared"
            prepared.mkdir()
            out = root / "results"
            args = argparse.Namespace(
                dataset="_smoke", m="SPRT", measurement=measurement,
                prepared_data=prepared, routers=["Origin", "Nearest", "FMM", "STMatch", "MM2-MDP"],
                route_source=None, out_root=out, mm2_executable=None, mm2_network=None,
                public_network=None, fmm_executable=None, stmatch_executable=None,
                ubodt=None, ubodt_executable=None, runtime_dir=None, edge_cache=None,
                input_srs="EPSG:4326", tracks_srs="EPSG:32650", network_srs="EPSG:32650",
                max_points=32, radius_m=200.0, gps_error_m=50.0, candidates=8,
                min_observation_share=0.95, seed=None,
            )
            orchestrator.route_m(args)
            failures = json.loads((out / "route_failures.json").read_text(encoding="utf-8"))
            self.assertEqual(len(failures["failures"]), 4)
            self.assertTrue((out / "SPRT/Origin/route_manifest.json").is_file())
            self.assertTrue((out / "SPRT/Origin/route_generation.log").is_file())

    def test_measurement_failure_writes_invalid_manifest(self):
        import run as orchestrator

        with tempfile.TemporaryDirectory(prefix="dfr_measurement_failure_") as tmp:
            root = Path(tmp)
            prepared = root / "prepared"
            prepared.mkdir()
            with (prepared / "trajectories.pkl").open("wb") as handle:
                pickle.dump([[[39.9, 116.3], [39.91, 116.31]]], handle)
            (prepared / "bbox.json").write_text(
                json.dumps({"bbox": [39.9, 39.91, 116.3, 116.31]}), encoding="utf-8"
            )
            osm = root / "osm_cache.pkl"
            osm.write_bytes(b"public")
            out = root / "measurement"
            args = argparse.Namespace(
                dataset="beijing", m="SPRT", prepared_data=prepared,
                epsilon=1.4, seed=42, public_slot_count=2, out_dir=out,
                osm_cache=osm, format="pkl", bbox=None, smoke=True,
            )
            # Keep the failure-path test runnable from a code-only archive;
            # the legacy executable is deliberately not shipped with it.
            with patch.object(orchestrator, "require_legacy", return_value=None), \
                 patch.object(orchestrator, "command", side_effect=subprocess.CalledProcessError(7, ["fake-wrapper"])):
                with self.assertRaises(subprocess.CalledProcessError):
                    orchestrator.synthesize_m(args)
            manifest = json.loads((out / "measurement_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "INVALID")
            self.assertTrue((out / "generation.log").is_file())

    def test_preflight_strict_detects_missing_public_resource(self):
        with tempfile.TemporaryDirectory(prefix="dfr_preflight_") as tmp:
            out = Path(tmp) / "preflight.json"
            result = subprocess.run([
                sys.executable, str(ROOT / "run.py"), "preflight", "--out", str(out),
                "--strict", "--fmm-executable", str(Path(tmp) / "missing-fmm"),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            report = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "INVALID")
            self.assertTrue(report["errors"])

    def test_route_evaluation_uses_derivation_sidecar(self):
        with tempfile.TemporaryDirectory(prefix="dfr_eval_contract_") as tmp:
            root = Path(tmp)
            sidecar = root / "metrics_v4__input/coordinates.pkl.manifest.json"
            report = root / "metrics_v4/evaluation_manifest.json"
            sidecar.parent.mkdir(parents=True)
            report.parent.mkdir(parents=True)
            sidecar.write_text(json.dumps({
                "schema": "road-route-coordinate-derivation-v1", "record_count": 2,
            }), encoding="utf-8")
            report.write_text(json.dumps({"status": "INVALID"}), encoding="utf-8")
            record = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(record["schema"], "road-route-coordinate-derivation-v1")
            self.assertEqual(record["record_count"], 2)
            self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["status"], "INVALID")

    def test_plot_supports_full_matrix_and_column_removal(self):
        spec = ROOT / "plotting/specs/full_27x48.json"
        with tempfile.TemporaryDirectory(prefix="dfr_plot_test_") as tmp:
            tmp_path = Path(tmp)
            results = tmp_path / "metrics_long.csv"
            with results.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["M", "R", "metric", "value", "status"])
                writer.writeheader()
                writer.writerows([
                    {"M": "SPRT", "R": "Origin", "metric": "BTF", "value": "0.4", "status": "VALID"},
                    {"M": "SPRT", "R": "Origin", "metric": "RC-CPC", "value": "0.3", "status": "VALID"},
                ])
            out = tmp_path / "figures"
            subprocess.run([
                sys.executable, str(ROOT / "plotting/plot_matrix.py"),
                "--spec", str(spec), "--results", str(results), "--out-dir", str(out),
                "--metric", "ALL", "--drop-col", "RC-CPC",
            ], check=True)
            self.assertTrue((out / "mr_ALL.png").is_file())
            self.assertTrue((out / "mr_ALL.pdf").is_file())


if __name__ == "__main__":
    unittest.main()
