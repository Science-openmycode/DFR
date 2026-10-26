"""Remove private research metadata from an existing DFR run manifest.

The route and transcript files are not rewritten.  A sanitized consumer
manifest is written in place, while fields that are useful only for local
research are preserved in research_metadata.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


PUBLIC_FIELDS = (
    "classification", "algorithm", "removed", "adjacency", "privacy",
    "public_slot_count", "fixed_output_slots", "paper_modified",
    "public_release_modified",
)
PRIVATE_FIELDS = (
    "research_seed", "formal_randomness", "oracle", "input_records",
    "tail_states", "family_release", "runtime_seconds",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sanitize(run_dir: Path) -> tuple[Path, Path]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    old = json.loads(manifest_path.read_text(encoding="utf-8"))
    outputs = {}
    for name in ("road_routes.pkl.gz", "dp_transcript.pkl.gz"):
        path = run_dir / name
        if path.is_file():
            outputs[name] = sha256(path)
    if not outputs:
        raise FileNotFoundError(f"no DFR output files found in {run_dir}")

    slots = old.get("public_slot_count", old.get("fixed_output_slots"))
    if not isinstance(slots, int) or slots <= 0:
        raise ValueError("manifest has no positive public slot count")
    public = {key: old[key] for key in PUBLIC_FIELDS if key in old}
    public["public_slot_count"] = slots
    public["fixed_output_slots"] = slots
    public["outputs"] = outputs
    public.setdefault("paper_modified", False)
    public.setdefault("public_release_modified", False)
    manifest_path.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")

    research = {key: old[key] for key in PRIVATE_FIELDS if key in old}
    research["sanitized_from_manifest"] = True
    research_path = run_dir / "research_metadata.json"
    research_path.write_text(json.dumps(research, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return manifest_path, research_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path,
                        help="one DFR run directory containing manifest.json")
    args = parser.parse_args()
    manifest, research = sanitize(args.run_dir.resolve())
    print(json.dumps({"manifest": str(manifest), "research_metadata": str(research)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
