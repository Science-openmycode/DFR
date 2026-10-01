"""Appendix visual in the same restrained style as appendix_mtnet_vs_mtr_beijing."""
from __future__ import annotations
import argparse,pickle,sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
PUBLIC=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PUBLIC))
from public_utils import filter_osm_ways_by_bbox,load_osm_ways

def load(p):
 with p.open('rb') as f:return [np.asarray(t,float) for t in pickle.load(f) if len(t)>=2]
def panel(ax,data,roads,bbox,title,note,color,alpha):
 base=[np.asarray([[p['lon'],p['lat']] for p in w['geometry']],float) for w in roads if len(w.get('geometry',[]))>=2]
 ax.add_collection(LineCollection(base,colors='#c8d9e5',linewidths=.22,alpha=.22,zorder=1))
 ax.add_collection(LineCollection([t[:,[1,0]] for t in data],colors=color,linewidths=.67,alpha=alpha,zorder=2))
 ax.set(xlim=(bbox[2],bbox[3]),ylim=(bbox[0],bbox[1]),aspect='equal');ax.set_xticks([]);ax.set_yticks([]);ax.set_title(title,fontsize=12.5,pad=7)
 ax.text(.015,.015,note,transform=ax.transAxes,fontsize=9,color='#555b61',va='bottom')
 for s in ax.spines.values():s.set_color('#222');s.set_linewidth(.8)
def main():
 p=argparse.ArgumentParser();p.add_argument('--real',type=Path,required=True);p.add_argument('--mtr',type=Path,required=True);p.add_argument('--puts',type=Path,required=True);p.add_argument('--osm-cache',type=Path,required=True);p.add_argument('--bbox',type=float,nargs=4,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();bbox=tuple(a.bbox)
 real,mtr,puts=load(a.real),load(a.mtr),load(a.puts);n=min(map(len,[real,mtr,puts]));real,mtr,puts=real[:n],mtr[:n],puts[:n];roads=filter_osm_ways_by_bbox(load_osm_ways(a.osm_cache),bbox)
 print(f'[plot] n={n}, common public roads={len(roads)}',flush=True);fig,axes=plt.subplots(1,3,figsize=(17.2,5.7),constrained_layout=True)
 panel(axes[0],real,roads,bbox,'Real GeoLife',f'{n:,} regional real trajectories','#2369a6',.58)
 panel(axes[1],mtr,roads,bbox,'MTR--DP-GSRT',f'{n:,} unconditional DP releases; $\\epsilon=1.0$','#07825e',.58)
 panel(axes[2],puts,roads,bbox,'PUTS native module',f'{n:,} releases; supplied 80-state preprocessing','#c84b7a',.62)
 fig.suptitle('Beijing small-region diagnostic: MTR road realization versus PUTS under its supplied preprocessing',fontsize=14,fontweight='bold')
 a.out.parent.mkdir(parents=True,exist_ok=True);fig.savefig(a.out,dpi=320,bbox_inches='tight');fig.savefig(a.out.with_suffix('.pdf'),bbox_inches='tight');print(a.out,flush=True)
if __name__=='__main__':main()
