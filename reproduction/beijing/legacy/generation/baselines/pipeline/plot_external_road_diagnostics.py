"""Render non-leaderboard road-network diagnostics for MTNet and PUTS."""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from public_utils import load_osm_ways, load_trajectories

REPO = ROOT.parent.parent
OUT = ROOT / 'outputs' / 'external_competitors' / 'figures'
MTNET = ROOT / 'outputs' / 'synthetic_releases' / 'external_competitors' / 'mtnet_dpsgd_public_seed.pkl'
MTR_BEIJING = ROOT / 'outputs' / 'synthetic_releases' / 'current_best' / 'mtr_dp_gsrt.pkl'
MTR_UCAR = ROOT / 'outputs' / 'synthetic_releases' / 'puts_ucar_dp_gsrt.pkl'
PUTS = REPO / 'MT_net' / 'puts_ucar_trajs.pkl'
UCAR = REPO / 'MT_net' / 'PUTS' / 'PUTS-main' / 'Dataset' / 'Ucar'


def read_ucar_real() -> list[np.ndarray]:
    out = []
    for line in (UCAR / 'pgeom.1000').read_text(encoding='utf-8', errors='ignore').splitlines():
        pts = []
        for token in line.split(';'):
            if ',' not in token:
                continue
            lon, lat = token.split(',', 1)
            try: pts.append([float(lat), float(lon)])
            except ValueError: pass
        if len(pts) >= 2: out.append(np.asarray(pts))
    return out


def read_ucar_roads() -> list[np.ndarray]:
    roads = []
    for line in (UCAR / 'geometry.txt').read_text(encoding='utf-8', errors='ignore').splitlines():
        pts = []
        for token in line.strip().replace('LINESTRING (', '').replace(')', '').split(','):
            values = token.strip().split()
            if len(values) >= 2:
                try: pts.append([float(values[1]), float(values[0])])
                except ValueError: pass
        if len(pts) >= 2: roads.append(np.asarray(pts))
    return roads


def draw(ax, trajectories, roads, bbox, color, title, note, *, trajectory_alpha=.10):
    for road in roads:
        ax.plot(road[:, 1], road[:, 0], color='#c9ced3', lw=.16, alpha=.20, zorder=1)
    segments = [np.asarray(t)[:, [1, 0]] for t in trajectories if len(t) >= 2]
    ax.add_collection(LineCollection(segments, colors=color, linewidths=.34,
                                    alpha=trajectory_alpha, zorder=2, rasterized=True))
    ax.set(xlim=(bbox[2], bbox[3]), ylim=(bbox[0], bbox[1]), title=title)
    ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
    ax.text(.02, .02, note, transform=ax.transAxes, fontsize=8, va='bottom', color='#31363b')


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    beijing_real = load_trajectories('geolife')
    with MTNET.open('rb') as f: mtnet = pickle.load(f)
    with MTR_BEIJING.open('rb') as f: mtr_beijing = pickle.load(f)
    with MTR_UCAR.open('rb') as f: mtr_ucar = pickle.load(f)
    ucar_real = read_ucar_real()
    with PUTS.open('rb') as f: puts = pickle.load(f)
    osm = []
    for way in load_osm_ways():
        pts = [[float(p['lat']), float(p['lon'])] for p in way.get('geometry', []) if 'lat' in p and 'lon' in p]
        if len(pts) >= 2: osm.append(np.asarray(pts))
    fig, axes = plt.subplots(2, 3, figsize=(19.6, 11), constrained_layout=True)
    draw(axes[0,0], beijing_real, osm, (39.75,40.15,116.10,116.65), '#1663a5',
         'Beijing real GeoLife', '17,123 trajectories; evaluation reference')
    draw(axes[0,1], mtr_beijing, osm, (39.75,40.15,116.10,116.65), '#147d64',
         'MTR--DP-GSRT full release', '17,123 releases; central-DP synthetic release', trajectory_alpha=.12)
    draw(axes[0,2], mtnet, osm, (39.75,40.15,116.10,116.65), '#c7362f',
         'MTNet DP-SGD with public random seeds',
         '17,123 releases; uniform public OSM start edges; zero time seed', trajectory_alpha=.25)
    ucar_bbox = (39.905,39.98,116.30,116.48)
    roads = read_ucar_roads()
    draw(axes[1,0], ucar_real, roads, ucar_bbox, '#1663a5',
         'UCAR real trajectories', '1,000 trajectories; PUTS native-scale dataset')
    draw(axes[1,1], mtr_ucar, roads, ucar_bbox, '#147d64',
         'MTR--DP-GSRT on UCAR', '1,000 releases; same native-scale input', trajectory_alpha=.15)
    draw(axes[1,2], puts, roads, ucar_bbox, '#8e44ad',
         'PUTS local reproduction', f'{len(puts):,} drawable trajectories; small-network diagnostic')
    fig.suptitle('External road-network diagnostics: distinct release protocols, not a common leaderboard', fontsize=13, fontweight='bold')
    fig.savefig(OUT / 'external_road_network_diagnostics.png', dpi=300, bbox_inches='tight')
    fig.savefig(OUT / 'external_road_network_diagnostics.pdf', bbox_inches='tight')
    paper = REPO / 'ARA_codex' / 'paper_latex' / 'figures'
    paper.mkdir(parents=True, exist_ok=True)
    fig.savefig(paper / 'external_road_network_diagnostics.png', dpi=300, bbox_inches='tight')
    fig.savefig(paper / 'external_road_network_diagnostics.pdf', bbox_inches='tight')


if __name__ == '__main__': main()
