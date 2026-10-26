"""Audit condition forwarding in a paired MTNet diagnostic output.

The paired diagnostic mode is intentionally not a DP synthetic release: it
passes each private source origin into the decoder.  This utility quantifies
the resulting origin and destination exposure without applying the conclusion
to MTNet's separate public-seed protocol.
"""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paired-routes", required=True, type=Path)
    parser.add_argument("--real-key", default="real_test_fmm")
    parser.add_argument("--synthetic-key", default="mtnet_non_dp")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    with args.paired_routes.open("rb") as handle:
        payload = pickle.load(handle)
    real = payload[args.real_key]
    synthetic = payload[args.synthetic_key]
    if len(real) != len(synthetic):
        raise ValueError("The condition exposure audit requires aligned diagnostic pairs.")
    real_start = np.asarray([route[0] for route in real], dtype=int)
    synthetic_start = np.asarray([route[0] for route in synthetic], dtype=int)
    real_end = np.asarray([route[-1] for route in real], dtype=int)
    synthetic_end = np.asarray([route[-1] for route in synthetic], dtype=int)
    report = {
        "scope": "private-condition diagnostic only; not a DP release",
        "pairs": int(len(real)),
        "origin_exact_recovery_rate": float(np.mean(real_start == synthetic_start)),
        "destination_exact_recovery_rate": float(np.mean(real_end == synthetic_end)),
        "unique_private_origins": int(len(set(real_start.tolist()))),
        "unique_released_origins": int(len(set(synthetic_start.tolist()))),
        "paired_input": str(args.paired_routes),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
