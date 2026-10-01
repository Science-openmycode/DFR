"""Render the strict FMM-prepared Beijing input and unmodified PUTS release."""
from __future__ import annotations
import argparse
import pickle
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection

PUBLIC = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PUBLIC))
from public_utils import filter_osm_ways_by_bbox, load_osm_ways
from plot_independent_mtr_puts import osm_tile_backdrop

def load(path: Path):
    with path.open('rb') as f: return [np.asarray(x, float) for x in pickle.load(f) if len(x)>=2]

def draw(ax, data, roads, bbox, title, color, backdrop):
    ax.set(xlim=(bbox[2],bbox[3]),ylim=(bbox[0],bbox[1]),aspect='equal')
    if backdrop is not None:
        image, extent=backdrop; ax.imshow(image,extent=extent,origin='upper',alpha=.50,zorder=0)
    base=[np.asarray([[p['lon'],p['lat']] for p in w['geometry']],float) for w in roads if len(w.get('geometry',[]))>=2]
    ax.add_collection(LineCollection(base,colors='#3d4a54',linewidths=.24,alpha=.18,zorder=1))
    ax.add_collection(LineCollection([t[:,[1,0]] for t in data],colors=color,linewidths=.74,alpha=.58,zorder=2))
    ax.set_xticks([]); ax.set_yticks([]); ax.set_title(title,fontsize=13,fontweight='bold',pad=8)
    for s in ax.spines.values(): s.set_color('#aab3bb'); s.set_linewidth(.55)

def main():
    p=argparse.ArgumentParser(); p.add_argument('--real',type=Path,required=True); p.add_argument('--puts',type=Path,required=True); p.add_argument('--osm-cache',type=Path,required=True); p.add_argument('--out',type=Path,required=True); p.add_argument('--bbox',nargs=4,type=float); p.add_argument('--no-basemap',action='store_true'); a=p.parse_args()
    real,puts=load(a.real),load(a.puts); n=min(len(real),len(puts)); real,puts=real[:n],puts[:n]
    points=np.vstack(real)
    if a.bbox: bbox=tuple(a.bbox)
    else:
        lo,hi=points.min(0),points.max(0); pad=.0015; bbox=(float(lo[0]-pad),float(hi[0]+pad),float(lo[1]-pad),float(hi[1]+pad))
    print(f'[1/2] strict matched input/release: n={n}, bbox={bbox}',flush=True)
    roads=filter_osm_ways_by_bbox(load_osm_ways(a.osm_cache),bbox)
    backdrop=None if a.no_basemap else osm_tile_backdrop(bbox,a.out.parent/'_osm_tile_cache')
    print('[2/2] rendering identical two-panel map comparison',flush=True)
    fig,axes=plt.subplots(1,2,figsize=(15.2,6.8),constrained_layout=True)
    draw(axes[0],real,roads,bbox,f'Real Beijing, FMM-accepted (n={n})','#2169a7',backdrop)
    draw(axes[1],puts,roads,bbox,f'PUTS upstream, unmodified (n={n})','#b24b88',backdrop)
    fig.suptitle('PUTS strict Beijing diagnostic: identical accepted corpus, release size, bbox, OSM background, and renderer',fontsize=14,fontweight='bold')
    a.out.parent.mkdir(parents=True,exist_ok=True); fig.savefig(a.out.with_suffix('.png'),dpi=320,bbox_inches='tight'); fig.savefig(a.out.with_suffix('.pdf'),bbox_inches='tight')
    print(f'wrote {a.out.with_suffix(".png")}',flush=True)
if __name__=='__main__': main()
