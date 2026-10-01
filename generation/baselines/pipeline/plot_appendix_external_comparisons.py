"""Render the two appendix-only external-comparator figures."""
from __future__ import annotations
import pickle, sys
from pathlib import Path
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from public_utils import load_osm_ways, load_trajectories

OUT = ROOT / 'outputs' / 'external_competitors' / 'figures'
BBOX = (39.75, 40.15, 116.10, 116.65)

def load(path):
    with open(path, 'rb') as f: return pickle.load(f)

def roads():
    return [np.asarray([[p['lat'], p['lon']] for p in w.get('geometry', []) if 'lat' in p and 'lon' in p])
            for w in load_osm_ways() if len(w.get('geometry', [])) >= 2]

def draw(ax, data, network, title, note, color):
    for line in network:
        if len(line) >= 2: ax.plot(line[:,1], line[:,0], color='#cbd1d7', lw=.14, alpha=.17, zorder=1)
    segs = [np.asarray(t)[:, [1,0]] for t in data if len(t) >= 2]
    ax.add_collection(LineCollection(segs, colors=color, linewidths=.32, alpha=.12, rasterized=True, zorder=2))
    ax.set(xlim=(BBOX[2], BBOX[3]), ylim=(BBOX[0], BBOX[1]), title=title); ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])
    ax.text(.02,.02,note,transform=ax.transAxes,fontsize=8,color='#30363b')

def figure_mtnet(network):
    real=load_trajectories('geolife'); mtr=load(ROOT/'outputs/synthetic_releases/current_best/mtr_dp_gsrt.pkl'); mt=load(ROOT/'outputs/synthetic_releases/external_competitors/mtnet_dpsgd_public_seed.pkl')
    fig,axs=plt.subplots(1,3,figsize=(16.4,5.2),constrained_layout=True)
    draw(axs[0],real,network,'Real GeoLife','17,123 real trajectories','#1764a5')
    draw(axs[1],mtr,network,'MTR--DP-GSRT','17,123 unconditional DP releases','#147d64')
    draw(axs[2],mt,network,'MTNet DP-SGD','17,123; uniform public OSM starts, zero time','#c7362f')
    fig.suptitle('Beijing full-release diagnostic: conditional road generation versus unconditional synthesis',fontweight='bold')
    fig.savefig(OUT/'appendix_mtnet_vs_mtr_beijing.png',dpi=300,bbox_inches='tight')
    fig.savefig(OUT/'appendix_mtnet_vs_mtr_beijing.pdf',bbox_inches='tight')

def figure_puts(network):
    base=ROOT/'outputs/external_competitors/puts_beijing_subset'
    real=load(base/'real_1000.pkl'); mtr=load(base/'mtr_dp_gsrt.pkl'); puts=load(base/'puts_1000.pkl')
    fig,axs=plt.subplots(1,3,figsize=(16.4,5.2),constrained_layout=True)
    draw(axs[0],real,network,'Beijing subset: real','1,000 records; PUTS 3,000-road adaptation','#1764a5')
    draw(axs[1],mtr,network,'MTR--DP-GSRT','1,000 fixed slots; reduced public candidate support','#147d64')
    draw(axs[2],puts,network,'PUTS adaptation','1,000 selected from its Beijing adapted output','#8e44ad')
    fig.suptitle('Beijing reduced-road diagnostic: not a full-city PUTS result',fontweight='bold')
    fig.savefig(OUT/'appendix_puts_vs_mtr_beijing_subset.png',dpi=300,bbox_inches='tight')
    fig.savefig(OUT/'appendix_puts_vs_mtr_beijing_subset.pdf',bbox_inches='tight')

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True); network=roads(); figure_mtnet(network); figure_puts(network)
