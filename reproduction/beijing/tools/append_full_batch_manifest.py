"""Record externally completed route/evaluation stages in a resumable batch manifest.

This is deliberately an append-only bookkeeping tool.  It never invents metric
values and it never changes a route output.  It is used when a route was run by
the dedicated FMM/STMatch command rather than by ``run_local_cli_batch.ps1``.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--dataset", default="beijing")
    parser.add_argument("--batch", default="batch_001")
    parser.add_argument("--methods", nargs="+", required=True)
    parser.add_argument("--routers", nargs="+", required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--measurement-root", type=Path, required=True)
    parser.add_argument("--prepared-data", type=Path, required=True)
    parser.add_argument("--public-network", type=Path, required=True)
    parser.add_argument("--edge-cache", type=Path, required=True)
    parser.add_argument("--fmm-executable", type=Path)
    parser.add_argument("--stmatch-executable", type=Path)
    parser.add_argument("--ubodt", type=Path)
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--status", default="DONE")
    args = parser.parse_args()

    # PowerShell's JSON writer may add a UTF-8 BOM; accept it without changing
    # the semantic manifest content.
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    stages = list(manifest.get("stages", []))
    existing = {str(item.get("name")) for item in stages}
    routers = list(manifest.get("routers", []))
    for router in args.routers:
        if router not in routers:
            routers.append(router)

    for method in args.methods:
        measurement = args.measurement_root / method / args.dataset / args.batch
        for router in args.routers:
            name = f"route:{method}+{router}"
            if name in existing:
                continue
            out = args.result_root / args.dataset / args.batch / method / router
            command = [
                "python", "run.py", "route-cell", "--dataset", args.dataset,
                "--m", method, "--r", router, "--measurement", str(measurement),
                "--prepared-data", str(args.prepared_data), "--out-dir", str(out),
            ]
            if router in {"FMM", "STMatch"}:
                command += ["--public-network", str(args.public_network), "--edge-cache", str(args.edge_cache)]
            if router == "FMM":
                if args.fmm_executable:
                    command += ["--fmm-executable", str(args.fmm_executable)]
                if args.ubodt:
                    command += ["--ubodt", str(args.ubodt)]
                if args.runtime_dir:
                    command += ["--runtime-dir", str(args.runtime_dir)]
            if router == "STMatch":
                if args.stmatch_executable:
                    command += ["--stmatch-executable", str(args.stmatch_executable)]
                if args.runtime_dir:
                    command += ["--runtime-dir", str(args.runtime_dir)]
            stages.append({
                "name": name,
                "output": str(out.resolve()),
                "command": command,
                "status": args.status,
                "recorded_by": "tools/append_full_batch_manifest.py",
            })

    # The fixed road-choice evaluator writes alongside ``data_results`` in the
    # batch root, while the merged table lives inside data_results.  Normalize
    # these paths even when this tool is run a second time to repair a manifest.
    bookkeeping = [
        ("road-choice-eval:FMM", args.result_root.parent / "road_choice_eval_fmm"),
        ("road-choice-eval:STMatch", args.result_root.parent / "road_choice_eval_stmatch"),
        ("merge-road-choice-metrics", args.result_root / args.dataset / args.batch / "metrics_long.csv"),
        ("audit-batch", args.manifest.parent / "full_batch_audit.json"),
    ]
    for name, output in bookkeeping:
        if name in existing:
            for stage in stages:
                if stage.get("name") == name:
                    stage["output"] = str(output.resolve())
                    break
        else:
            stages.append({
                "name": name,
                "output": str(output.resolve()),
                "status": args.status,
                "recorded_by": "tools/append_full_batch_manifest.py",
            })

    manifest["routers"] = routers
    manifest["stages"] = stages
    manifest["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["notes"] = [
        "FMM and STMatch route cells were executed with the aligned public network/edge cache and recorded after the initial local batch driver.",
        "MM2-MDP cells remain MISSING until all chunks of each M are complete; no old mismatched cache is reused.",
        "DPMM, MTNet, and MTR-DFR are native rows and are not inferred or copied into M×R cells.",
        "Road-choice metrics are present only where the fixed evaluator emitted them; BTF/EdgeCPC/TurnCPC/FamilyCPC remain missing when not computed.",
    ]
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(args.manifest.resolve()), "stages": len(stages), "routers": routers}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
