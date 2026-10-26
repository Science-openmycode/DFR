from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np


CHECK_DIR = Path(__file__).resolve().parent
PUBLIC_RELEASE = CHECK_DIR.parent
if str(PUBLIC_RELEASE) not in sys.path:
    sys.path.insert(0, str(PUBLIC_RELEASE))

from public_utils import load_trajectories  # noqa: E402


DEFAULT_PRIVTRACE_ROOT = CHECK_DIR / "official_repos" / "privtrace" / "PrivTrace-main"


def write_privtrace_format(path: Path, trajs: list[np.ndarray], precision: int, max_points_per_traj: int | None) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = f"{{:.{int(precision)}f}}"
    written = 0
    points_total = 0
    with path.open("w", encoding="utf-8") as f:
        for i, tr in enumerate(trajs):
            arr = np.asarray(tr, dtype=float)
            if arr.ndim != 2 or arr.shape[1] < 2 or len(arr) < 2:
                continue
            if max_points_per_traj is not None and len(arr) > max_points_per_traj:
                idx = np.linspace(0, len(arr) - 1, int(max_points_per_traj)).round().astype(int)
                arr = arr[idx]
            # PrivTrace's README uses x,y. Our public trajectory arrays are lat,lon;
            # write lon,lat so x/y follows the common geographic convention.
            f.write(f"#{written}:\n")
            pts = [fmt.format(float(lon)) + "," + fmt.format(float(lat)) for lat, lon in arr[:, :2]]
            f.write(">0:" + ";".join(pts) + ";\n")
            written += 1
            points_total += len(pts)
    return {"trajectories": written, "points_total": points_total}


def main() -> int:
    ap = argparse.ArgumentParser(description="Export public trajectory data to the official PrivTrace README format.")
    ap.add_argument("--data", default="geolife", help="Named public data source or serialized trajectory path.")
    ap.add_argument("--limit", type=int, default=400, help="Number of trajectories to export; omit with -1 for full loaded data.")
    ap.add_argument("--out-name", default=None, help="Output file under official PrivTrace datasets/.")
    ap.add_argument("--out", type=Path, default=None, help="Explicit output path.")
    ap.add_argument("--precision", type=int, default=6)
    ap.add_argument(
        "--max-points-per-traj",
        type=int,
        default=None,
        help="Optional deterministic within-trajectory downsampling for official-code feasibility.",
    )
    args = ap.parse_args()

    limit = None if int(args.limit) < 0 else int(args.limit)
    trajs = load_trajectories(args.data, limit=limit)
    if args.out is not None:
        out = args.out
    else:
        name = args.out_name or f"codex_{args.data}_{'full' if limit is None else limit}.dat"
        out = DEFAULT_PRIVTRACE_ROOT / "datasets" / name
    summary = write_privtrace_format(out, trajs, int(args.precision), args.max_points_per_traj)
    print(
        "{"
        f"\"data\":\"{args.data}\","
        f"\"out\":\"{out}\","
        f"\"trajectories\":{summary['trajectories']},"
        f"\"points_total\":{summary['points_total']}"
        "}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
