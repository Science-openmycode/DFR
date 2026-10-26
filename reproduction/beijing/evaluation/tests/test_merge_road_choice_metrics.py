from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ISOLATED_ROOT = Path(__file__).resolve().parents[2]
if str(ISOLATED_ROOT) not in sys.path:
    sys.path.insert(0, str(ISOLATED_ROOT))

from tools import merge_road_choice_metrics


def test_merge_preserves_source_column_and_existing_rows(tmp_path: Path, monkeypatch) -> None:
    batch = tmp_path / "batch"
    table = batch / "data_results" / "beijing" / "batch_001" / "metrics_long.csv"
    table.parent.mkdir(parents=True)
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["dataset", "batch", "M", "R", "metric", "value", "status", "source"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "dataset": "beijing",
                "batch": "batch_001",
                "M": "SPRT",
                "R": "Origin",
                "metric": "Grid",
                "value": "0.1",
                "status": "VALID",
                "source": "cell_evaluation",
            }
        )
    route_dir = batch / "data_results" / "beijing" / "batch_001" / "SPRT" / "FMM"
    route_dir.mkdir(parents=True)
    (route_dir / "route_manifest.json").write_text(
        json.dumps({"records": 3, "reasons": {"accepted": 2, "disconnected": 1}}),
        encoding="utf-8",
    )
    source_dir = tmp_path / "road_choice"
    source_dir.mkdir()
    (source_dir / "metrics.json").write_text(
        json.dumps(
            {
                "results": {
                    "SPRT": {
                        "road_choice_cpc": 0.5,
                        "road_choice_ndcg": 0.6,
                        "next_road_accuracy": 0.7,
                        "next_road_nll": 1.0,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "merge_road_choice_metrics.py",
            "--batch",
            str(batch),
            "--metrics",
            f"FMM={source_dir}",
        ],
    )

    merge_road_choice_metrics.main()

    with table.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["source"] == "cell_evaluation"
    assert {row["metric"] for row in rows} == {
        "Grid",
        "RoadYield",
        "RC-CPC",
        "RC-NDCG",
        "NextRoadAcc",
        "NextRoadNLL",
    }
    assert all("source" in row for row in rows)

