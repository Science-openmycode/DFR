"""Inspect a real-source/matched-reference binding without generating anything."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "evaluation"))
from experiment_contract import validate_real_reference, POPULATIONS
from route_metric_core import load_pickle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real-source", type=Path, required=True)
    parser.add_argument("--real-matched", type=Path, required=True)
    parser.add_argument("--edge-cache", type=Path, required=True)
    parser.add_argument("--network", type=Path)
    parser.add_argument("--population", choices=POPULATIONS, default="full-corpus")
    parser.add_argument("--report", type=Path, help="Private local audit, never distribute with a release")
    args = parser.parse_args()
    if args.report and args.report.exists():
        parser.error("Choose a new report path")
    try:
        result = {"status": "passed", **validate_real_reference(args.real_matched, args.real_source,
                  load_pickle(args.edge_cache), args.population, args.network)}
        code = 0
    except (ValueError, FileNotFoundError, KeyError) as exc:
        result = {"status": "rejected", "population": args.population, "reason": str(exc),
                  "classification": "PRIVATE_EXPERIMENT_AUDIT_NOT_FOR_RELEASE"}
        code = 2
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
