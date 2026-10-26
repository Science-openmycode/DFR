from __future__ import annotations

import argparse
import hashlib
import math
import shutil
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42
matplotlib.rcParams["ps.fonttype"] = 42
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection

PUBLIC_RELEASE = Path(__file__).resolve().parents[1]
if str(PUBLIC_RELEASE) not in sys.path:
    sys.path.insert(0, str(PUBLIC_RELEASE))

from public_utils import PUBLIC_ROOT, filter_osm_ways_by_bbox, load_osm_ways, load_trajectories, write_json


REAL_COLOR = "#7A7A7A"
MTR_COLOR = "#009E73"
OSM_COLOR = "#9AA0A6"
BACKGROUND = "#FCFCFA"

METHOD_LABELS = {
    # Frozen KDD full-release names.  Keep these exact labels in figures and
    # tables so the renderer never silently falls back to an older adapter name.
    "sprt_full": "SPRT",
    "privtrace_full": "PrivTrace",
    "dptrajpm_full": "DPTraj-PM",
    "mtr_public_only_full": "MTR-public-only",
    "mtr_dp_gsrt_full": "MTR-GSRT",
    "dpmm_official_rdpseed_full": "DPMM (official)",
    "dpmm_official_rdpseed_subset300": "DPMM (official)",
    "dpmm_official_rdpseed_prefix300_visual": "DPMM (official)",
    "sprt-native": "SPRT-native",
    "sprt_native": "SPRT-native",
    "sprt-paper-structured": "SPRT-native",
    "sprt_paper_structured": "SPRT-native",
    "sprt-osm": "SPRT-OSM",
    "sprt_osm": "SPRT-OSM",
    "privtrace-native": "PrivTrace-native",
    "privtrace_native": "PrivTrace-native",
    "privtrace-official": "PrivTrace-native",
    "privtrace_official": "PrivTrace-native",
    "privtrace-osm": "PrivTrace-OSM",
    "privtrace_osm": "PrivTrace-OSM",
    "dptrajpm-native": "DPTrajPM-native",
    "dptrajpm_native": "DPTrajPM-native",
    "dptraj-pm-native": "DPTrajPM-native",
    "dptrajpm-official": "DPTrajPM-native",
    "dptrajpm_official": "DPTrajPM-native",
    "dptrajpm-osm": "DPTrajPM-OSM",
    "dptrajpm_osm": "DPTrajPM-OSM",
    "dptraj-pm-osm": "DPTrajPM-OSM",
    "dpstd-native": "DPStd-native",
    "dpstd_native": "DPStd-native",
    "dpstd-osm": "DPStd-OSM",
    "dpstd_osm": "DPStd-OSM",
    "ara-dp-gsrt": "MTR-GSRT",
    "ara_dp_gsrt": "MTR-GSRT",
    "dp-gsrt": "MTR-GSRT",
    "dp_gsrt": "MTR-GSRT",
    "mtr-dp-gsrt": "MTR-GSRT",
    "mtr_dp_gsrt": "MTR-GSRT",
    "dp_gsrt_portal_qrsp": "MTR-GSRT",
    "dp_request_public_shortest_path_control": "MTR-public-only",
    "mtnet-road-edge-local": "MTNet road-edge (local)",
    "mtnet_road_edge_local": "MTNet road-edge (local)",
    "mtnet-audited": "MTNet road-edge (local)",
    "mtnet_audited": "MTNet road-edge (local)",
    "mtnet_dpsgd_public_seed": "MTNet (DP-SGD, public seeds)",
    "puts_scaled_local": "PUTS (scaled local reproduction)",
}

METHOD_ORDER = [
    "SPRT",
    "PrivTrace",
    "DPTraj-PM",
    "SPRT-native",
    "SPRT-OSM",
    "PrivTrace-native",
    "PrivTrace-OSM",
    "DPTrajPM-native",
    "DPTrajPM-OSM",
    "DPStd-native",
    "DPStd-OSM",
    "MTNet road-edge (local)",
    "MTNet (DP-SGD, public seeds)",
    "PUTS (scaled local reproduction)",
    "MTR-public-only",
    "MTR-GSRT",
    "DPMM (official)",
]

METHOD_COLORS = {
    "Real": REAL_COLOR,
    "SPRT": "#D55E00",
    "PrivTrace": "#CC79A7",
    "DPTraj-PM": "#E69F00",
    "MTR-public-only": "#2A7F62",
    "SPRT-native": "#D55E00",
    "SPRT-OSM": "#F18F01",
    "PrivTrace-native": "#CC79A7",
    "PrivTrace-OSM": "#B358B2",
    "DPTrajPM-native": "#E69F00",
    "DPTrajPM-OSM": "#BF812D",
    "DPStd-native": "#56B4E9",
    "DPStd-OSM": "#878787",
    "MTNet road-edge (local)": "#1565C0",
    "MTNet (DP-SGD, public seeds)": "#1976D2",
    "PUTS (scaled local reproduction)": "#8E44AD",
    "MTR-GSRT": MTR_COLOR,
    "DPMM (official)": "#007C91",
}

FIGURE2_CAPTION = (
    "Beijing full-size visual comparison. Every panel uses the same bbox, "
    "OSM background, plotting parameters, and n=17,123 trajectories. Native "
    "methods produce chords and templates; MTR/DP-GSRT follows connected road "
    "corridors but currently covers a narrower subset of the city than the "
    "real corpus. The corresponding quantitative road-layer comparison is "
    "reported in the full-release metric table."
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_path(path: str | Path) -> str:
    """Prefer a public-root-relative POSIX path in portable manifests."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(PUBLIC_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def log(message: str) -> None:
    print(f"[plot] {time.strftime('%H:%M:%S')} {message}", flush=True)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Plot real and already-generated synthetic trajectory releases under "
            "a shared map protocol. This script does not synthesize data."
        )
    )
    p.add_argument("--real", default="geolife")
    p.add_argument("--real-limit", type=int, default=None, help="public limit for loading the real reference corpus")
    p.add_argument("--synthetic", action="append", default=[], help="synthetic file; repeatable")
    p.add_argument("--synthetic-dir", default=None, help="directory containing synthetic releases")
    p.add_argument("--osm-cache", default="data/osm/osm_cache_beijing.pkl")
    p.add_argument("--out-dir", default=str(PUBLIC_ROOT / "outputs" / "figures_full"))
    p.add_argument("--name", default="shared_protocol_full")
    p.add_argument("--display-count", default="all", help="'all' or an integer; use same count for every panel")
    p.add_argument(
        "--strict-full-size",
        action="store_true",
        help="enforce the Figure-2 full-release protocol: no sampling and every panel has expected-count trajectories",
    )
    p.add_argument("--expected-count", type=int, default=None, help="required trajectory count in strict-full-size mode")
    p.add_argument(
        "--require-methods",
        default=None,
        help="comma-separated required panel labels; use 'beijing-figure2' for the paper Figure 2 method set",
    )
    p.add_argument("--paper-figure2-style", action="store_true", help="use the high-contrast paper Figure 2 style")
    p.add_argument(
        "--landscape-1x5",
        action="store_true",
        help="force the current Beijing Figure-2 layout to one row x five panels",
    )
    p.add_argument(
        "--landscape-1x6",
        action="store_true",
        help="Use one compact row for exactly six paper panels.",
    )
    p.add_argument(
        "--landscape-2x5",
        action="store_true",
        help="force the Beijing Figure-2 layout to 2 rows x 5 columns",
    )
    p.add_argument(
        "--landscape-2x6",
        action="store_true",
        help="force a 2 rows x 6 columns layout; use after adding one direct road-edge competitor to Figure 2",
    )
    p.add_argument("--copy-to-paper", action="store_true", help="copy outputs to paper_latex/figures/beijing_published_vs_ara_map")
    p.add_argument("--title", default=None)
    p.add_argument("--caption", default=None)
    p.add_argument("--max-panels", type=int, default=999)
    p.add_argument("--seed", type=int, default=2026)
    p.add_argument("--max-osm-ways", type=int, default=0, help="maximum OSM ways drawn per panel; 0 means all")
    p.add_argument("--line-alpha", type=float, default=None)
    p.add_argument("--line-width", type=float, default=None)
    p.add_argument("--road-alpha", type=float, default=None)
    p.add_argument("--road-width", type=float, default=None)
    p.add_argument("--dpi", type=int, default=300)
    return p


def full_bbox(trajs: list[np.ndarray], pad_ratio: float = 0.025) -> tuple[float, float, float, float]:
    pts = np.vstack([np.asarray(t, dtype=float)[:, :2] for t in trajs if len(t) >= 2])
    mn = pts.min(axis=0)
    mx = pts.max(axis=0)
    span = np.maximum(mx - mn, 1e-9)
    return (
        float(mn[0] - pad_ratio * span[0]),
        float(mx[0] + pad_ratio * span[0]),
        float(mn[1] - pad_ratio * span[1]),
        float(mx[1] + pad_ratio * span[1]),
    )


def discover_synthetic(paths: list[str], synthetic_dir: str | None) -> list[Path]:
    found = [Path(p) for p in paths]
    if synthetic_dir:
        root = Path(synthetic_dir)
        if not root.is_absolute():
            root = Path.cwd() / root
        for suffix in ["*.npz", "*.pkl", "*.pickle", "*.npy"]:
            found.extend(sorted(root.glob(suffix)))
    seen = set()
    by_stem: dict[str, Path] = {}
    priority = {".npz": 0, ".pkl": 1, ".pickle": 1, ".npy": 2}
    for path in found:
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.exists() and str(path) not in seen:
            key = str(path.with_suffix(""))
            prev = by_stem.get(key)
            if prev is None or priority.get(path.suffix.lower(), 9) < priority.get(prev.suffix.lower(), 9):
                by_stem[key] = path
            seen.add(str(path))
    out = sorted(by_stem.values(), key=lambda p: method_sort_key(pretty_label(p)))
    if not out:
        raise RuntimeError("provide existing --synthetic and/or --synthetic-dir")
    return out


def normalize_method_key(stem: str) -> str:
    return stem.lower().replace(" ", "_").replace("__", "_")


def pretty_label(path: Path) -> str:
    if (
        path.name == "trajectories.pkl"
        and "active_hierarchy_release" in path.parent.name
    ):
        return "MTR-GSRT"
    key = normalize_method_key(path.stem)
    key_dash = key.replace("_", "-")
    direct = METHOD_LABELS.get(key, METHOD_LABELS.get(key_dash))
    if direct is not None:
        return direct
    # Public reruns often prefix/suffix method names with dataset and seed tags,
    # e.g., geolife_sprt_native_s42. Match the longest known method token.
    matches: list[tuple[int, str]] = []
    for method_key, label in METHOD_LABELS.items():
        token = method_key.replace("-", "_")
        if token in key or method_key in key_dash:
            matches.append((len(token), label))
    if matches:
        matches.sort(reverse=True)
        return matches[0][1]
    return path.stem


def method_sort_key(label: str) -> tuple[int, str]:
    try:
        return (METHOD_ORDER.index(label), label)
    except ValueError:
        return (len(METHOD_ORDER), label.lower())


def display_sample(trajs: list[np.ndarray], display_count: str, rng: np.random.Generator) -> list[np.ndarray]:
    if display_count.lower() == "all":
        return list(trajs)
    n = int(display_count)
    if len(trajs) <= n:
        return list(trajs)
    idx = rng.choice(len(trajs), size=n, replace=False)
    return [trajs[int(i)] for i in idx]


def draw_osm(ax, osm_ways: list[dict], bbox, road_alpha: float, road_width: float, max_ways: int) -> None:
    lat_min, lat_max, lon_min, lon_max = bbox
    ways = osm_ways if max_ways <= 0 else osm_ways[:max_ways]
    total = len(ways)
    all_segments = []
    for i, way in enumerate(ways, start=1):
        if i == 1 or i == total or i % 10000 == 0:
            log(f"drawing OSM ways {i:,}/{total:,}")
        geom = way.get("geometry", []) if isinstance(way, dict) else []
        pts = []
        segments = []
        for p in geom:
            if "lat" not in p or "lon" not in p:
                continue
            lat = float(p["lat"])
            lon = float(p["lon"])
            if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                pts.append((lon, lat))
            elif pts:
                segments.append(pts)
                pts = []
        if len(pts) >= 2:
            segments.append(pts)
        all_segments.extend(seg for seg in segments if len(seg) >= 2)
    if all_segments:
        ax.add_collection(
            LineCollection(
                all_segments,
                colors=OSM_COLOR,
                linewidths=road_width,
                alpha=road_alpha,
                zorder=1,
                rasterized=True,
            )
        )


def draw_trajs(ax, trajs: list[np.ndarray], color: str, alpha: float, width: float) -> None:
    total = len(trajs)
    segments = []
    for i, tr in enumerate(trajs, start=1):
        if i == 1 or i == total or i % 5000 == 0:
            log(f"drawing trajectories {i:,}/{total:,}")
        arr = np.asarray(tr, dtype=float)
        if len(arr) >= 2:
            segments.append(arr[:, [1, 0]])
    if segments:
        ax.add_collection(
            LineCollection(
                segments,
                colors=color,
                linewidths=width,
                alpha=alpha,
                zorder=2,
                rasterized=True,
            )
        )


def panel_grid(
    n: int,
    landscape_1x5: bool = False,
    landscape_1x6: bool = False,
    landscape_2x5: bool = False,
    landscape_2x6: bool = False,
) -> tuple[int, int]:
    if sum((landscape_1x5, landscape_1x6, landscape_2x5, landscape_2x6)) > 1:
        raise RuntimeError("choose at most one fixed landscape layout")
    if landscape_1x5:
        if n != 5:
            raise RuntimeError(f"--landscape-1x5 requires exactly 5 panels, got {n}")
        return 1, 5
    if landscape_1x6:
        if n != 6:
            raise RuntimeError(f"--landscape-1x6 requires exactly 6 panels, got {n}")
        return 1, 6
    if landscape_2x5:
        if n != 10:
            raise RuntimeError(f"--landscape-2x5 requires exactly 10 panels, got {n}")
        return 2, 5
    if landscape_2x6:
        if n not in {11, 12}:
            raise RuntimeError(f"--landscape-2x6 requires 11 or 12 panels, got {n}")
        return 2, 6
    cols = min(4, max(1, math.ceil(math.sqrt(n))))
    rows = int(math.ceil(n / cols))
    return rows, cols


def style_values(args) -> tuple[float, float, float, float]:
    if args.paper_figure2_style:
        return (
            0.12 if args.line_alpha is None else args.line_alpha,
            0.30 if args.line_width is None else args.line_width,
            0.105 if args.road_alpha is None else args.road_alpha,
            0.18 if args.road_width is None else args.road_width,
        )
    return (
        0.18 if args.line_alpha is None else args.line_alpha,
        0.36 if args.line_width is None else args.line_width,
        0.22 if args.road_alpha is None else args.road_alpha,
        0.22 if args.road_width is None else args.road_width,
    )


def panel_alpha(label: str, base_alpha: float, paper_style: bool) -> float:
    if not paper_style:
        return base_alpha
    if label == "Real":
        return min(base_alpha, 0.085)
    if label == "MTR-GSRT":
        return max(base_alpha, 0.145)
    if label.endswith("-OSM"):
        return max(base_alpha, 0.135)
    return base_alpha


def parse_required_methods(require_methods: str | None) -> list[str]:
    if not require_methods:
        return []
    if require_methods.strip().lower() == "beijing-figure2":
        return [
            "SPRT-native",
            "PrivTrace-native",
            "DPTrajPM-native",
            "DPStd-native",
            "MTR-GSRT",
        ]
    return [item.strip() for item in require_methods.split(",") if item.strip()]


def validate_strict_counts(
    real: list[np.ndarray],
    loaded_panels: list[tuple[str, Path, list[np.ndarray]]],
    display_count: str,
    expected_count: int | None,
    require_methods: str | None,
) -> int:
    if display_count.lower() != "all":
        raise RuntimeError(
            "strict-full-size mode requires --display-count all. "
            "Do not use sampled panels for Figure 2."
        )
    expected = expected_count if expected_count is not None else len(real)
    if len(real) != expected:
        raise RuntimeError(f"real panel count mismatch: expected {expected}, got {len(real)}")
    bad = [(label, path, len(trajs)) for label, path, trajs in loaded_panels if len(trajs) != expected]
    if bad:
        detail = "; ".join(f"{label} ({path.name}) has {count}" for label, path, count in bad)
        raise RuntimeError(
            f"synthetic panel count mismatch under Figure-2 protocol; expected {expected}. {detail}. "
            "Regenerate full-size releases before plotting."
        )
    required = parse_required_methods(require_methods)
    if required:
        present = {label for label, _path, _trajs in loaded_panels}
        missing = [label for label in required if label not in present]
        if missing:
            raise RuntimeError(
                "required Figure-2 methods are missing: "
                + ", ".join(missing)
                + ". Regenerate all baseline and MTR/DP-GSRT full-size releases before plotting."
            )
    return expected


def main() -> None:
    args = build_parser().parse_args()
    t0 = time.time()
    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    limit_note = "full corpus" if args.real_limit is None else f"first {args.real_limit:,} public-protocol trajectories"
    log(f"loading real trajectories from {args.real} ({limit_note})")
    real = load_trajectories(args.real, limit=args.real_limit)
    log(f"loaded {len(real):,} real trajectories")
    log(f"loading OSM cache from {args.osm_cache}")
    bbox = full_bbox(real)
    osm_ways_raw = load_osm_ways(args.osm_cache)
    osm_ways = filter_osm_ways_by_bbox(osm_ways_raw, bbox)
    log(f"loaded {len(osm_ways_raw):,} OSM ways; kept {len(osm_ways):,} near bbox")
    syn_paths = discover_synthetic(args.synthetic, args.synthetic_dir)
    syn_paths = syn_paths[: max(1, args.max_panels - 1)]
    log(f"found {len(syn_paths):,} synthetic release file(s) to plot")
    rng = np.random.default_rng(args.seed)

    loaded_syn: list[tuple[str, Path, list[np.ndarray]]] = []
    for i, path in enumerate(syn_paths, start=1):
        log(f"[{i}/{len(syn_paths)}] loading {path.name}")
        trajs = load_trajectories(str(path), limit=None)
        log(f"[{i}/{len(syn_paths)}] loaded {len(trajs):,} trajectories as {pretty_label(path)}")
        loaded_syn.append((pretty_label(path), path, trajs))
    loaded_syn = sorted(loaded_syn, key=lambda x: method_sort_key(x[0]))
    if args.strict_full_size:
        validate_strict_counts(real, loaded_syn, args.display_count, args.expected_count, args.require_methods)

    panels: list[dict] = [
        {
            "label": "Real",
            "path": args.real,
            "loaded_count": len(real),
            "trajs": display_sample(real, args.display_count, rng),
            "color": METHOD_COLORS["Real"],
        }
    ]
    for label, path, trajs in loaded_syn:
        panels.append(
            {
                "label": label,
                "path": str(path.resolve()),
                "loaded_count": len(trajs),
                "trajs": display_sample(trajs, args.display_count, rng),
                "color": METHOD_COLORS.get(label, "#377EB8"),
            }
        )

    log("computing shared full-real bbox")
    bbox = full_bbox(real)
    line_alpha, line_width, road_alpha, road_width = style_values(args)
    rows, cols = panel_grid(
        len(panels),
        landscape_1x5=args.landscape_1x5,
        landscape_1x6=args.landscape_1x6,
        landscape_2x5=args.landscape_2x5,
        landscape_2x6=args.landscape_2x6,
    )
    if args.landscape_1x6:
        per_w, per_h = 3.7, 3.05
    elif args.landscape_1x5 or args.landscape_2x5 or args.landscape_2x6:
        per_w, per_h = 4.4, 4.05
    else:
        per_w = 5.2 if args.paper_figure2_style else 4.1
        per_h = 4.8 if args.paper_figure2_style else 4.1
    fig, axes = plt.subplots(rows, cols, figsize=(per_w * cols, per_h * rows), constrained_layout=True)
    fig.patch.set_facecolor(BACKGROUND)
    axes = np.asarray(axes).reshape(-1)
    for ax in axes[len(panels) :]:
        ax.axis("off")
    for panel_i, (ax, panel) in enumerate(zip(axes, panels), start=1):
        label = str(panel["label"])
        trajs = panel["trajs"]
        color = str(panel["color"])
        log(f"[panel {panel_i}/{len(panels)}] rendering {label} with {len(trajs):,} trajectories")
        ax.set_facecolor(BACKGROUND)
        draw_osm(ax, osm_ways, bbox, road_alpha, road_width, args.max_osm_ways)
        draw_trajs(ax, trajs, color, panel_alpha(label, line_alpha, args.paper_figure2_style), line_width)
        ax.set_xlim(bbox[2], bbox[3])
        ax.set_ylim(bbox[0], bbox[1])
        ax.set_aspect("equal", adjustable="box")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_linewidth(0.55)
            spine.set_color("#D3D6DA")
        ax.set_title(f"{label}\nn={len(trajs):,}", fontsize=9, fontweight="bold")
    title = args.title or (
        "Beijing full-size visual comparison (n=17,123 per panel)"
        if args.paper_figure2_style
        else "Shared road-network visualization protocol"
    )
    fig.suptitle(title, fontsize=12, fontweight="bold")

    png = out_dir / f"{args.name}.png"
    pdf = out_dir / f"{args.name}.pdf"
    log(f"saving PNG -> {png}")
    fig.savefig(png, dpi=args.dpi, bbox_inches="tight")
    log(f"saving PDF -> {pdf}")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    copied_outputs = {}
    if args.copy_to_paper:
        raise RuntimeError(
            "--copy-to-paper was retired: the public code release does not contain manuscript sources; "
            "use the files under --out-dir"
        )
    caption = args.caption or (FIGURE2_CAPTION if args.paper_figure2_style else "")
    manifest = {
        "command_role": "plot_trajectory_panels",
        "renderer": manifest_path(Path(__file__)),
        "renderer_sha256": sha256_file(Path(__file__).resolve()),
        "protocol": "figure2_full_size" if args.strict_full_size else "shared_visualization",
        "caption": caption,
        "real": manifest_path(args.real) if Path(args.real).exists() else args.real,
        "real_sha256": (
            sha256_file(Path(args.real).resolve()) if Path(args.real).is_file() else None
        ),
        "real_limit": args.real_limit,
        "synthetic_files": [manifest_path(p) for p in syn_paths],
        "synthetic_sha256": {
            manifest_path(p): sha256_file(p.resolve()) for p in syn_paths
        },
        "panels": [
            {
                "label": str(panel["label"]),
                "path": manifest_path(panel["path"]),
                "loaded_count": int(panel["loaded_count"]),
                "plotted_count": int(len(panel["trajs"])),
            }
            for panel in panels
        ],
        "display_count": args.display_count,
        "expected_count": args.expected_count,
        "required_methods": parse_required_methods(args.require_methods),
        "strict_full_size": bool(args.strict_full_size),
        "count_matched": len({len(panel["trajs"]) for panel in panels}) == 1,
        "visual_sampling": args.display_count.lower() != "all",
        "max_osm_ways": int(args.max_osm_ways),
        "bbox": [float(x) for x in bbox],
        "bbox_source": "real full dataset",
        "osm_cache": manifest_path(Path(args.osm_cache).resolve() if Path(args.osm_cache).is_absolute() else (Path.cwd() / args.osm_cache).resolve()),
        "osm_sha256": sha256_file(
            Path(args.osm_cache).resolve()
            if Path(args.osm_cache).is_absolute()
            else (Path.cwd() / args.osm_cache).resolve()
        ),
        "same_bbox_for_all_panels": True,
        "same_osm_for_all_panels": True,
        "same_plotting_parameters_for_all_panels": True,
        "style": {
            "layout": "1x5" if args.landscape_1x5 else ("1x6" if args.landscape_1x6 else ("2x5" if args.landscape_2x5 else ("2x6" if args.landscape_2x6 else f"{rows}x{cols}"))),
            "background": BACKGROUND,
            "osm_color": OSM_COLOR,
            "road_alpha": road_alpha,
            "road_width": road_width,
            "line_alpha_base": line_alpha,
            "line_width": line_width,
            "dpi": int(args.dpi),
        },
        "outputs": {"png": manifest_path(png), "pdf": manifest_path(pdf), **copied_outputs},
        "output_sha256": {"png": sha256_file(png), "pdf": sha256_file(pdf)},
    }
    write_json(out_dir / f"{args.name}.json", manifest)
    if caption:
        (out_dir / f"{args.name}.caption.txt").write_text(caption + "\n", encoding="utf-8")
    log(f"completed in {time.time() - t0:.1f}s")
    print(f"wrote {png}")
    print(f"wrote {pdf}")
    if copied_outputs:
        print(f"copied to {copied_outputs['paper_png']}")


if __name__ == "__main__":
    main()
