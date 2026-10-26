from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import expand_metric_matrix


def _write_table(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["dataset", "batch", "M", "R", "metric", "value", "status", "source"],
        )
        writer.writeheader()
        writer.writerow({
            "dataset": "beijing", "batch": "batch_001", "M": "SPRT", "R": "FMM",
            "metric": "grid_density_jsd", "value": "0.25", "status": "VALID",
            "source": "cell_evaluation",
        })


def test_expands_every_frozen_row_and_metric_without_fabricating_values(tmp_path: Path) -> None:
    spec = ROOT / "plotting" / "specs" / "full_27x48.json"
    source = tmp_path / "metrics_long.csv"
    output = tmp_path / "metrics_full.csv"
    _write_table(source)

    rows = expand_metric_matrix.expand_table(spec, source)
    expand_metric_matrix.write_rows(rows, output)

    frozen = json.loads(spec.read_text(encoding="utf-8"))
    assert len(rows) == len(frozen["rows"]) * len(frozen["columns"])
    values = {(r["row"], r["column"]): r for r in rows}
    assert values[("SPRT + FMM", "Grid")]["status"] == "VALID"
    assert values[("SPRT + FMM", "Grid")]["value"] == "0.25"
    missing = values[("SPRT + FMM", "BTF")]
    assert missing["status"] == "MISSING"
    assert missing["value"] == ""


def test_alias_is_only_used_for_exact_metric_name(tmp_path: Path) -> None:
    spec = ROOT / "plotting" / "specs" / "full_27x48.json"
    source = tmp_path / "metrics_long.csv"
    _write_table(source)
    rows = expand_metric_matrix.expand_table(spec, source)
    grid = [r for r in rows if r["column"] == "Grid" and r["row"] == "SPRT + FMM"]
    assert len(grid) == 1
    assert grid[0]["source_metric"] == "grid_density_jsd"
    # A similarly named route metric must not be copied to unrelated columns.
    btf = [r for r in rows if r["column"] == "BTF" and r["row"] == "SPRT + FMM"]
    assert btf[0]["status"] == "MISSING"

