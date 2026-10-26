"""Convert the documented 3,000-road PUTS Beijing subset into a MTR input."""
from __future__ import annotations
import argparse
import pickle
from pathlib import Path
import numpy as np

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--puts-input', type=Path, default=None)
    p.add_argument('--puts-out', type=Path, default=None)
    p.add_argument('--limit', type=int, default=1000)
    a = p.parse_args()
    result = []
    for line in a.input.read_text(encoding='utf-8', errors='ignore').splitlines()[:a.limit]:
        points = []
        for token in line.split(';'):
            try:
                lon, lat = map(float, token.split(',', 1)); points.append([lat, lon])
            except ValueError:
                continue
        if len(points) >= 2: result.append(np.asarray(points, dtype=float))
    if len(result) != a.limit:
        raise RuntimeError(f'expected {a.limit} drawable trajectories, got {len(result)}')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open('wb') as f: pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)
    if (a.puts_input is None) != (a.puts_out is None):
        p.error('--puts-input and --puts-out must be supplied together')
    if a.puts_input is not None:
        with a.puts_input.open('rb') as f: puts = pickle.load(f)
        drawable = [np.asarray(t, dtype=float)[:, :2] for t in puts if len(t) >= 2]
        if len(drawable) < a.limit:
            raise RuntimeError(f'PUTS has only {len(drawable)} drawable trajectories')
        a.puts_out.parent.mkdir(parents=True, exist_ok=True)
        with a.puts_out.open('wb') as f: pickle.dump(drawable[:a.limit], f, protocol=pickle.HIGHEST_PROTOCOL)

if __name__ == '__main__': main()
