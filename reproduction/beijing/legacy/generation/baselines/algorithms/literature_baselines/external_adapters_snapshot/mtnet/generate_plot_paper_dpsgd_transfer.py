"""Plot a count-matched Beijing transfer from the Algorithm-1 MTNet trainer.

This is deliberately separate from the non-DP transfer plotter.  It consumes
only a saved fixed-B Algorithm-1 model and the public FMM road representation.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import random
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
import torch


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--mtnet-root', type=Path, required=True,
                   help='Unmodified official MTNet source extracted from the author archive')
    p.add_argument('--data-parent', type=Path, required=True)
    p.add_argument('--city', default='beijing_fmm_l20')
    p.add_argument('--prepared', type=Path, required=True)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--max-route-edges', type=int, default=20)
    p.add_argument('--seed', type=int, default=20260712)
    p.add_argument('--sample-batch-size', type=int, default=256)
    p.add_argument('--condition-source', choices=['public', 'private-diagnostic'], default='public',
                   help='public uses data-independent OSM edge/time seeds; private-diagnostic reuses real origins')
    p.add_argument('--release-size', type=int, required=True,
                   help='Public fixed release-size protocol constant')
    a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=True)

    root = a.mtnet_root.resolve(); os.chdir(root); sys.path.insert(0, str(root))
    from util import config
    config.DATA_BASE = str(a.data_parent.resolve()) + os.sep
    config.CITY = a.city
    config.TRAJ_FIX_LEN = a.max_route_edges + 1
    random.seed(a.seed); np.random.seed(a.seed); torch.manual_seed(a.seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(a.seed)
    from util.dataloader import load_trajs_raw
    import mtnet

    train, test = load_trajs_raw()
    # Real paths are evaluation data only; they are never fed to the public
    # release generator unless the explicit private-diagnostic mode is chosen.
    trajs = torch.cat([train[0], test[0]], dim=0)
    dpts = torch.cat([train[1], test[1]], dim=0)
    tcosts = torch.cat([train[2], test[2]], dim=0)
    checkpoint = torch.load(a.model, map_location=config.device)
    model = mtnet.Model(); model.load_state_dict(checkpoint['state_dict']); model.eval()

    # PyTorch-version compatibility only: preserve integral time-slot values.
    official_step = model.step
    def dtype_compatibility_step(xt, dptslot, hs, cs):
        return official_step(xt, dptslot.long(), hs, cs)
    model.step = dtype_compatibility_step

    if a.condition_source == 'public':
        rng = np.random.default_rng(a.seed)
        edge_count = model.adj.size(0) - 1  # exclude the terminal mask row
        gen_x = torch.as_tensor(rng.integers(1, edge_count, size=(a.release_size, 1)), dtype=torch.long)
        gen_dpts = torch.zeros((a.release_size, 1), dtype=dpts.dtype)
        gen_tcosts = torch.zeros((a.release_size, 1), dtype=tcosts.dtype)
        generation_note = 'public data-independent OSM origin edges and zero time slots'
    else:
        gen_x, gen_dpts, gen_tcosts = trajs[:, :1], dpts[:, :1], tcosts[:, :1]
        generation_note = 'PRIVATE diagnostic conditioning on real origin edges and times; not a DP release'
    generated_batches = []
    with torch.no_grad():
        for start in range(0, len(gen_x), a.sample_batch_size):
            stop = min(len(gen_x), start + a.sample_batch_size)
            generated, _ = model.sample(gen_x[start:stop].to(config.device),
                                        gen_dpts[start:stop].to(config.device),
                                        gen_tcosts[start:stop].to(config.device))
            generated_batches.append(generated.cpu())
    generated = torch.cat(generated_batches, dim=0)
    synth = []
    for origin, suffix in zip(gen_x[:, 0].tolist(), generated.cpu().tolist()):
        route = [int(origin)]
        for edge in suffix:
            if edge == 0: break
            route.append(int(edge))
        synth.append(route)
    real = [[int(edge) for edge in route if int(edge) != 0] for route in trajs.tolist()]

    gdf = gpd.read_file(a.prepared / 'fmm_network.shp')
    geoms = {int(row.id): row.geometry for row in gdf.itertuples()}
    fig, axes = plt.subplots(1, 2, figsize=(16, 7.4), constrained_layout=True)
    panels = [(real, 'Original FMM-matched GeoLife trajectories', '#0077a8'),
              (synth, 'MTNet Algorithm-1 DP-SGD public-seed release', '#d94841')]
    for ax, (routes, title, color) in zip(axes, panels):
        gdf.plot(ax=ax, color='#d5d9dc', linewidth=0.20, alpha=0.22)
        segments = [np.asarray(geoms[edge].coords) for route in routes for edge in route if edge in geoms]
        ax.add_collection(LineCollection(segments, colors=color, linewidths=0.42,
                                         alpha=0.10, rasterized=True))
        ax.set_title(f'{title}\n(n={len(routes)}; same fixed-L population and public OSM)', fontsize=11)
        ax.set_axis_off(); ax.set_aspect('equal')
    fig.suptitle(f'Beijing count-matched MTNet transfer under the fixed L={a.max_route_edges} protocol', fontsize=14, y=1.02)
    fig.savefig(a.out / 'beijing_mtnet_paper_dpsgd_full_population.png', dpi=280, bbox_inches='tight')
    with (a.out / 'full_population_routes.pkl').open('wb') as f:
        pickle.dump({'real_fmm_L20': real, 'mtnet_paper_dpsgd': synth}, f)
    manifest = {
        'protocol': f'full retained Beijing FMM population with fixed L={a.max_route_edges}; count-matched visualization',
        'n_real': len(real), 'n_synthetic': len(synth), 'seed': a.seed,
        'condition_source': a.condition_source, 'generation_note': generation_note,
        'model_checkpoint': str(a.model), 'privacy_note': checkpoint.get(
            'privacy_unit', 'Read paper_algorithm_manifest.json for DP provenance.'),
        'warning': 'The figure inherits the checkpoint provenance. It is not evidence of author-hyperparameter numerical reproduction unless the checkpoint manifest establishes that separately.',
    }
    (a.out / 'visualization_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
