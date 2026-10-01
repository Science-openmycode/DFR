"""Create a reproducible drivable-road cache from a public OSM way cache.

This is a public-data preparation step.  It excludes footways, paths, steps,
and cycleways so an MTR road decoder is not offered pedestrian-only routes.
"""
from __future__ import annotations

import argparse
import json
import pickle
from collections import Counter
from pathlib import Path


DRIVABLE_HIGHWAYS = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service", "road",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter a public OSM cache to drivable ways.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--summary", type=Path, default=None)
    args = parser.parse_args()
    with args.input.open("rb") as handle:
        source = pickle.load(handle)
    kept = []
    for way in source:
        tags = way.get("tags", {}) if isinstance(way, dict) else {}
        highway = str(tags.get("highway", ""))
        if highway not in DRIVABLE_HIGHWAYS:
            continue
        if str(tags.get("access", "")).lower() in {"no", "private"}:
            continue
        if len(way.get("geometry", [])) >= 2:
            kept.append(way)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("wb") as handle:
        pickle.dump(kept, handle, pickle.HIGHEST_PROTOCOL)
    summary = {
        "source": str(args.input),
        "public_filter": "drivable highway classes excluding footway/path/steps/cycleway and access=no/private",
        "n_source_ways": len(source),
        "n_drivable_ways": len(kept),
        "highway_counts": dict(sorted(Counter(w.get("tags", {}).get("highway", "") for w in kept).items())),
    }
    target = args.summary or args.out.with_suffix(".json")
    target.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {len(kept):,} drivable public OSM ways -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
