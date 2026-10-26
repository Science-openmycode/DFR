from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from experiment_contract import validate_attack_release


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute release-only membership attacks against one synthetic trajectory corpus."
    )
    parser.add_argument("--method", default=None, help="Display name for a single --release path.")
    parser.add_argument("--members", required=True)
    parser.add_argument("--nonmembers", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--release", action="append", required=True,
                        help="Repeat NAME=PATH for a batch, or give PATH with --method.")
    parser.add_argument("--bbox", nargs=4, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260724)
    parser.add_argument("--attack-manifest", type=Path, required=True,
                        help="Private split manifest binding training, members and disjoint nonmembers")
    parser.add_argument("--synthesis-lineage", action="append", required=True,
                        help="NAME=executed train-only generation record; one per release")
    args = parser.parse_args()
    output = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    if output.exists():
        parser.error("Choose a new attack output directory")
    releases = []
    for item in args.release:
        if "=" in item:
            name, raw_path = item.split("=", 1)
        else:
            name, raw_path = args.method, item
        if not name or not raw_path:
            parser.error("--release must be PATH with --method or NAME=PATH")
        releases.append((name, Path(raw_path).resolve()))
    if len({name for name, _ in releases}) != len(releases):
        parser.error("release names must be unique")
    lineage_items = [value.split("=", 1) for value in args.synthesis_lineage]
    if any(len(item) != 2 for item in lineage_items):
        parser.error("--synthesis-lineage expects NAME=PATH")
    lineage = dict(lineage_items)
    if len(lineage) != len(lineage_items) or set(lineage) != {name for name, _ in releases}:
        parser.error("Provide exactly one synthesis lineage per release")
    validated = {name: validate_attack_release(args.attack_manifest, Path(lineage[name]), release,
                  Path(args.members), Path(args.nonmembers), Path(args.reference)) for name, release in releases}
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    command_log = []
    for name, release in releases:
        safe_name = "".join(character if character.isalnum() or character in "-_" else "_" for character in name)
        population = output / "raw" / safe_name / "population_linkage.json"
        gda_root = output / "raw" / safe_name / "gda_mia"
        population.parent.mkdir(parents=True, exist_ok=True)
        commands = [
            [sys.executable, str(ROOT / "evaluation" / "pipeline" / "evaluate_population_linkage.py"),
             "--members", str(Path(args.members).resolve()), "--nonmembers", str(Path(args.nonmembers).resolve()),
             "--release", str(release), "--out", str(population),
             "--landmarks", "16", "--seed", str(args.seed)],
            [sys.executable, str(ROOT / "evaluation" / "pipeline" / "evaluate_gda_mia.py"),
             "--members", str(Path(args.members).resolve()), "--nonmembers", str(Path(args.nonmembers).resolve()),
             "--reference", str(Path(args.reference).resolve()), "--release", name,
             str(release), "--bbox", *args.bbox, "--out", str(gda_root),
             "--landmarks", "8", "--seed", str(args.seed)],
        ]
        for command in commands:
            print("RUN:", subprocess.list2cmdline(command), flush=True)
            subprocess.run(command, cwd=ROOT, check=True)
            command_log.append(command)
        population_result = json.loads(population.read_text(encoding="utf-8"))
        gda_result = json.loads(gda_root.with_suffix(".json").read_text(encoding="utf-8"))
        gda_row = gda_result["rows"][0]
        rows.append({"method": name,
                     "Population-linkage AUC": population_result["auc"],
                     "GDA-MIA AUC": gda_row.get("auc", gda_row.get("aucroc"))})
    result = output / "results.csv"
    with result.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    (output / "manifest.json").write_text(json.dumps({
        "protocol": "train_bound_membership_attacks_v3", "commands": command_log,
        "private_input_validation": validated,
        "result": str(result.resolve())
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote executed attack scores to {result}")


if __name__ == "__main__":
    main()
