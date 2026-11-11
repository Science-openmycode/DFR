"""Redraw the verified MR cell table without accessing experimental inputs."""
from pathlib import Path
import argparse,hashlib,json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mr_renderer_core import visualization as v

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def remove_explanatory_text(fig):
 for text in list(fig.texts):text.remove()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--epsilon',type=float,required=True);p.add_argument('--slots',type=int,default=15730);a=p.parse_args()
 cells=json.loads(a.data.read_text('utf-8-sig'))
 methods=list(dict.fromkeys(c['row'] for c in cells));metrics=list(dict.fromkeys(c['metric'] for c in cells))
 assert len(metrics)==11 and len(cells)==len(methods)*len(metrics)
 assert len({(c['row'],c['metric']) for c in cells})==len(cells)
 assert not any(c['status']=='MISSING' for c in cells)
 a.out.mkdir(parents=True,exist_ok=False)
 plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':10,'axes.unicode_minus':False,'pdf.fonttype':42})
 original_save=v.save
 def save(fig,out,name):
  ax=fig.axes[0];labels=[t.get_text().replace('MTNet_DP_OD_coarse24','MTNet + DP-OD') for t in ax.get_xticklabels()]
  ax.set_xticks(range(len(labels)),labels,rotation=62,ha='right',fontsize=8)
  remove_explanatory_text(fig)
  original_save(fig,out,name)
 v.LABELS[1]='(b) 代表路线\n十区平均覆盖率';v.save=save
 try:v.matrix(cells,methods,metrics,a.out)
 finally:v.save=original_save
 (a.out/'cells.json').write_text(json.dumps(cells,ensure_ascii=False,indent=2),encoding='utf-8')
 assert json.loads((a.out/'cells.json').read_text('utf-8'))==cells
 manifest=dict(status='PASS',scope='saved-results plotting only',epsilon=a.epsilon,shape=[11,len(methods)],cells=len(cells),missing=0,input_sha256=sha(a.data),renderer_sha256=sha(Path(v.__file__)),entry_sha256=sha(__file__),outputs={x.name:sha(x) for x in a.out.iterdir() if x.is_file()})
 manifest['explanatory_title_and_footers_removed']=True
 (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
 print(f'MR_REPLAY_PASS: all{len(cells)} cells preserved')
if __name__=='__main__':main()
