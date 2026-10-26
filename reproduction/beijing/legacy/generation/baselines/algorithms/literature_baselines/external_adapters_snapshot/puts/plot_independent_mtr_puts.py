"""Render Real, independent full-OSM MTR, and original PUTS under one protocol."""
from __future__ import annotations

import argparse
import pickle
import sys
import math
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
from PIL import Image

PUBLIC_RELEASE = Path(__file__).resolve().parents[2]
if str(PUBLIC_RELEASE) not in sys.path:
    sys.path.insert(0, str(PUBLIC_RELEASE))
from public_utils import filter_osm_ways_by_bbox, load_osm_ways


def load(path: Path) -> list[np.ndarray]:
    with path.open("rb") as handle:
        return [np.asarray(x, dtype=float) for x in pickle.load(handle) if len(x) >= 2]


def _tile_x(lon: float, zoom: int) -> float:
    return (lon + 180.0) / 360.0 * (2 ** zoom)


def _tile_y(lat: float, zoom: int) -> float:
    lat = min(max(lat, -85.05112878), 85.05112878)
    return (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * (2 ** zoom)


def _lon_from_x(x: float, zoom: int) -> float:
    return x / (2 ** zoom) * 360.0 - 180.0


def _lat_from_y(y: float, zoom: int) -> float:
    return math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / (2 ** zoom)))))


def osm_tile_backdrop(bbox: tuple[float, float, float, float], cache_dir: Path, zoom: int = 14):
    """Fetch one cached OSM tile mosaic with bounded network waits.

    Fetching once before subplot creation keeps every panel pixel-identical and
    avoids contextily's repeated unbounded tile requests in headless runs.
    """
    lat_min, lat_max, lon_min, lon_max = bbox
    x0, x1 = math.floor(_tile_x(lon_min, zoom)), math.floor(_tile_x(lon_max, zoom))
    y0, y1 = math.floor(_tile_y(lat_max, zoom)), math.floor(_tile_y(lat_min, zoom))
    cache_dir.mkdir(parents=True, exist_ok=True)
    canvas = Image.new("RGB", ((x1 - x0 + 1) * 256, (y1 - y0 + 1) * 256), "white")
    try:
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                tile_path = cache_dir / str(zoom) / str(x) / f"{y}.png"
                if tile_path.exists():
                    tile = Image.open(tile_path).convert("RGB")
                else:
                    # urllib is deliberately used here rather than requests:
                    # on this Windows proxy it reliably closes each public
                    # tile connection instead of timing out after five seconds.
                    content = None
                    last_error = None
                    for url in [
                        f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png",
                        f"https://a.tile.openstreetmap.fr/osmfr/{zoom}/{x}/{y}.png",
                    ]:
                        try:
                            request = Request(url, headers={"User-Agent": "ARA-Codex-research/1.0", "Connection": "close"})
                            with urlopen(request, timeout=30) as response:
                                content = response.read()
                            break
                        except (OSError, URLError) as error:
                            last_error = error
                    if content is None:
                        raise RuntimeError(f"could not retrieve tile {zoom}/{x}/{y}: {last_error}")
                    tile_path.parent.mkdir(parents=True, exist_ok=True)
                    tile_path.write_bytes(content)
                    tile = Image.open(tile_path).convert("RGB")
                canvas.paste(tile, ((x - x0) * 256, (y - y0) * 256))
    except Exception as error:
        print(f"[warn] public OSM tile backdrop unavailable ({error}); using cached road overlay only.", flush=True)
        return None
    return np.asarray(canvas), (_lon_from_x(x0, zoom), _lon_from_x(x1 + 1, zoom), _lat_from_y(y1 + 1, zoom), _lat_from_y(y0, zoom))


def draw(ax, data: list[np.ndarray], roads: list[dict], bbox: tuple[float, float, float, float], title: str, color: str, backdrop) -> None:
    ax.set(xlim=(bbox[2], bbox[3]), ylim=(bbox[0], bbox[1]), aspect="equal")
    if backdrop is not None:
        image, extent = backdrop
        ax.imshow(image, extent=extent, origin="upper", alpha=.52, zorder=0)
    road_lines = [np.asarray([[p["lon"], p["lat"]] for p in w["geometry"]], float) for w in roads if len(w.get("geometry", [])) >= 2]
    ax.add_collection(LineCollection(road_lines, colors="#3e4a54", linewidths=.24, alpha=.22 if backdrop is not None else .52, zorder=1))
    lines = [t[:, [1, 0]] for t in data]
    ax.add_collection(LineCollection(lines, colors=color, linewidths=.62, alpha=.50, zorder=2))
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(title, fontsize=11.5, fontweight="bold", pad=7)
    for s in ax.spines.values(): s.set_color("#aab3bb"); s.set_linewidth(.55)


def main() -> None:
    ap = argparse.ArgumentParser(description="Shared full-city drawing protocol for independent MTR and PUTS")
    ap.add_argument("--real", type=Path, required=True)
    ap.add_argument("--mtr", type=Path, required=True)
    ap.add_argument("--puts", type=Path, required=True)
    ap.add_argument("--osm-cache", type=Path, required=True)
    ap.add_argument("--bbox", nargs=4, type=float, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--no-basemap", action="store_true", help="disable the shared OpenStreetMap tile backdrop")
    args = ap.parse_args(); bbox = tuple(args.bbox)
    print("[1/2] Loading independent releases and common public-map backdrop...", flush=True)
    real, mtr, puts = load(args.real), load(args.mtr), load(args.puts)
    # A release comparison is count-matched.  The caller may provide a larger
    # source corpus, but the renderer must never silently plot more real lines
    # than synthetic lines.
    n = min(len(real), len(mtr), len(puts))
    real, mtr, puts = real[:n], mtr[:n], puts[:n]
    roads = filter_osm_ways_by_bbox(load_osm_ways(args.osm_cache), bbox)
    backdrop = None if args.no_basemap else osm_tile_backdrop(bbox, args.out.parent / "_osm_tile_cache")
    print(f"[2/2] Rendering 3 panels, n={len(real):,} per panel...", flush=True)
    fig, axes = plt.subplots(1, 3, figsize=(17.0, 5.65), constrained_layout=True)
    draw(axes[0], real, roads, bbox, f"Real Beijing subset (n={len(real):,})", "#2369a6", backdrop)
    draw(axes[1], mtr, roads, bbox, f"MTR / DP-GSRT (n={len(mtr):,})", "#07825e", backdrop)
    draw(axes[2], puts, roads, bbox, f"Original PUTS native module (n={len(puts):,})", "#b34b8e", backdrop)
    fig.suptitle("Independent-method comparison: identical raw subset, release size, bbox, public map, and renderer", fontsize=13.2, fontweight="bold")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out.with_suffix(".png"), dpi=320, bbox_inches="tight")
    fig.savefig(args.out.with_suffix(".pdf"), bbox_inches="tight")
    print(f"Wrote {args.out.with_suffix('.png')} and PDF", flush=True)


if __name__ == "__main__":
    main()
