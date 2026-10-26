from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools" / "merge_edge_route_metrics.py"


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = ["dataset", "batch", "M", "R", "metric", "value", "status", "source"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_edge_merge_replaces_coordinate_and_protects_native(tmp_path: Path) -> None:
    table = tmp_path / "metrics_long.csv"
    edge = tmp_path / "edge.csv"
    write_csv(table, [
        {"dataset": "beijing", "batch": "batch_001", "M": "SPRT", "R": "FMM",
         "metric": "BTF", "value": "0.1", "status": "VALID", "source": "cell_evaluation"},
        {"dataset": "beijing", "batch": "batch_001", "M": "MTR-DFR", "R": "Native",
         "metric": "BTF", "value": "0.9", "status": "VALID", "source": "native_scores:x"},
    ])
    write_csv(edge, [
        {"dataset": "beijing", "batch": "batch_001", "M": "SPRT", "R": "FMM",
         "metric": "BTF", "value": "0.3", "status": "VALID", "source": "edge_id_route_metrics"},
        {"dataset": "beijing", "batch": "batch_001", "M": "MTR-DFR", "R": "Native",
         "metric": "BTF", "value": "0.2", "status": "VALID", "source": "edge_id_route_metrics"},
        {"dataset": "beijing", "batch": "batch_001", "M": "SPRT", "R": "FMM",
         "metric": "not_road", "value": "0.4", "status": "VALID", "source": "edge_id_route_metrics"},
    ])
    subprocess.run([sys.executable, str(TOOL), "--table", str(table),
                    "--edge-metrics", str(edge)], check=True)
    rows = list(csv.DictReader(table.open(encoding="utf-8", newline="")))
    assert next(r for r in rows if r["M"] == "SPRT")["value"] == "0.3"
    assert next(r for r in rows if r["M"] == "SPRT")["source"] == "edge_id_route_metrics"
    native = next(r for r in rows if r["M"] == "MTR-DFR")
    assert native["value"] == "0.9"
    payload = json.loads((tmp_path / "edge_route_metrics_merge_manifest.json").read_text())
    assert payload["replaced_rows"] == 1
    assert payload["skipped_native_rows"] == 1
