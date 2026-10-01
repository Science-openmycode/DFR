"""Visual sanity check for the bundled paper-protocol PUTS UCAR release."""
from __future__ import annotations
import argparse
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
import numpy as np
from audit_original_ucar_protocol import parse_pgeom

def roads(path: Path):
    out=[]
    for line in path.read_text(errors="ignore").splitlines():
        pts=[]
        for token in line.strip().removeprefix("LINESTRING (").removesuffix(")").split(","):
            try: lon,lat=token.split()[:2]; pts.append([float(lon),float(lat)])
            except ValueError: pass
        if len(pts)>=2: out.append(np.asarray(pts))
    return out
def draw(ax,data,base,title,color):
    ax.add_collection(LineCollection(base,colors="#6a7780",linewidths=.18,alpha=.18))
    ax.add_collection(LineCollection([x[:,[1,0]] for x in data],colors=color,linewidths=.46,alpha=.20))
    pts=np.vstack(base);ax.set(xlim=(pts[:,0].min(),pts[:,0].max()),ylim=(pts[:,1].min(),pts[:,1].max()),aspect="equal",title=title)
    ax.set_xticks([]);ax.set_yticks([])
def main():
    p=argparse.ArgumentParser();p.add_argument('--puts-root',type=Path,required=True);p.add_argument('--synthetic',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    root=a.puts_root; base=roads(root/'Dataset/Ucar/geometry.txt');real=parse_pgeom(root/'Dataset/Ucar/pgeom.1000',False);syn=parse_pgeom(a.synthetic,True)
    fig,ax=plt.subplots(1,2,figsize=(12,5),constrained_layout=True);draw(ax[0],real,base,f'UCAR real (n={len(real):,})','#2166a5');draw(ax[1],syn,base,f'PUTS, original protocol (n={len(syn):,})','#0a8160')
    a.out.parent.mkdir(parents=True,exist_ok=True);fig.savefig(a.out,dpi=300,bbox_inches='tight')
if __name__=='__main__':main()
