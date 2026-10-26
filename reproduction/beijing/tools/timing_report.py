"""Extract measured stage timings from one local reproducibility batch."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


TIME_RE = re.compile(r"Time takes(?: excluding input)? ([0-9.]+)")
MM2_RE = re.compile(r"Matching finished in ([0-9.]+) s")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.batch.resolve()
    rows: list[dict] = []
    measurement_root = root / "synthetic_data" / "measurements"
    for manifest in sorted(measurement_root.glob("*/beijing/batch_001/baseline_wrapper_manifest.json")):
        data = read_json(manifest)
        rows.append({"stage": "synthesize-m", "method": manifest.parts[-4], "runtime_sec": data.get("elapsed_sec"), "source": str(manifest)})
    data_root = root / "data_results" / "beijing" / "batch_001"
    for manifest in sorted(data_root.glob("*/Origin/metrics/manifest.json")):
        data = read_json(manifest)
        rows.append({"stage": "evaluate-cell", "method": manifest.parts[-4], "router": "Origin", "runtime_sec": data.get("elapsed_sec"), "source": str(manifest)})
    for manifest in sorted(data_root.glob("*/*/metrics/manifest.json")):
        data = read_json(manifest)
        router = manifest.parts[-3]
        method = manifest.parts[-4]
        if router == "Origin":
            continue
        rows.append({"stage": "evaluate-cell", "method": method, "router": router, "runtime_sec": data.get("elapsed_sec"), "source": str(manifest)})
    for manifest in sorted(data_root.glob("*/*/route_manifest.json")):
        data = read_json(manifest)
        text = json.dumps(data.get("invocation", {}).get("stdout", ""))
        values = [float(value) for value in TIME_RE.findall(text)]
        if values:
            rows.append({"stage": "route-cell-external", "method": data.get("M"), "router": data.get("R"), "runtime_sec": values[-1], "source": str(manifest)})
    for log in sorted(data_root.glob("*/MM2-MDP/mm2_batches/*/run/mm2_stdout.log")):
        values = [float(value) for value in MM2_RE.findall(log.read_text(encoding="utf-8", errors="replace"))]
        if values:
            rows.append({"stage": "route-cell-external", "method": log.parts[-6], "router": "MM2-MDP", "chunk": log.parts[-3], "runtime_sec": values[-1], "source": str(log)})
    measured = [row for row in rows if isinstance(row.get("runtime_sec"), (int, float))]
    totals: dict[str, float] = {}
    for row in measured:
        totals[row["stage"]] = totals.get(row["stage"], 0.0) + float(row["runtime_sec"])
    report = {
        "schema_version": 1,
        "batch": str(root),
        "measured_rows": rows,
        "measured_totals_sec": totals,
        "note": "Only runtimes explicitly recorded by a manifest or external matcher log are measured; future native methods and other cities require separate runs and are not inferred here.",
    }
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(args.out.resolve()), "measured_rows": len(rows), "totals_sec": totals}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
