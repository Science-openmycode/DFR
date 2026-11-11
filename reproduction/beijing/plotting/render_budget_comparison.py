"""Replot frozen results, without training, scoring or accessing private trajectories."""
import argparse,csv,hashlib,importlib.util,json,math,time,sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'reference_results/budget_comparison'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def validate_plot_rows(rows,allow_partial=False):
    """Keep explicitly pending values blank instead of inventing scores."""
    missing=0
    for row in rows:
        if row['value']=='':
            if not allow_partial or row.get('status')!='MISSING' or str(row['n'])!='0':
                raise ValueError('Missing points require partial mode and MISSING/n=0')
            missing+=1
        elif not math.isfinite(float(row['value'])) or (row['sd'] and not math.isfinite(float(row['sd']))):
            raise ValueError('Non-finite completed score')
    return missing

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--representative-label',default='Representative coverage (5 routes) ↑')
    p.add_argument('--allow-partial',action='store_true',help='Leave explicitly pending budget points as gaps')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    s=BASE/'sources/github'
    assert sha(s/'budget_current.png')=='771342ec94e9054c4412de90ca070c1b0c4a30ada6cd232bc5bca836a570288f'
    assert 'reproduction/beijing/reference_results/sensitivity_current/figures/budget/budget_current.png' in (s/'README.md').read_text('utf-8')
    spec=importlib.util.spec_from_file_location('original',s/'render_current_sweeps.py');original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
    original.render('budget',s/'source_summary.json',s/'application_summary.json',a.out/'original_redraw')
    assert read(s/'plot_data.json')==read(a.out/'original_redraw/plot_data.json')
    rows=list(csv.DictReader(a.data.open(encoding='utf-8-sig')))
    missing=validate_plot_rows(rows,a.allow_partial)
    order=['PrivTrace','AdaTrace','DPTraj-PM','MTNet','MTNet+DP-OD','DFR']
    present={r['method'] for r in rows}
    if present-set(order):raise ValueError('Unknown method names: '+str(present-set(order)))
    methods=[m for m in order if m in present];eps=[.2,.4,.7,1,1.4,2,3]
    lookup={(r['method'],float(r['epsilon']),r['metric']):r for r in rows}
    assert len(rows)==len(lookup)==len(methods)*7*11
    plt.rcParams.update({'font.size':8,'font.family':'DejaVu Sans','pdf.fonttype':42})
    fig,axes=plt.subplots(3,4,figsize=(13,6.4),layout='constrained');limits={}
    for i,(ax,(_,metric,title)) in enumerate(zip(axes.flat,original.PANELS)):
        bounds=[]
        styles=dict(zip(order,zip(['#D55E00','#009E73','#CC79A7','#E69F00','#0072B2','#222222'],['s','^','D','v','o','*'],['--','-.','--','-.',':','-'])))
        for method in methods:
            color,marker,style=styles[method]
            g=[lookup[method,e,metric] for e in eps];y=np.array([float(r['value']) if r['value']!='' else np.nan for r in g]);sd=np.array([float(r['sd']) if r['sd'] else 0 for r in g])
            valid=np.isfinite(y)
            bounds.extend((y-sd)[valid]);bounds.extend((y+sd)[valid])
            if method=='DFR':ax.fill_between(eps,y-sd,y+sd,color=color,alpha=.10)
            ax.plot(eps,y,color=color,marker=marker,ls=style,lw=1.7 if method=='DFR' else 1.3,ms=6 if method=='AdaTrace' else 4.7 if method=='DFR' else 3,label='DFR (native R)' if method=='DFR' else method)
        low,high=min(bounds),max(bounds);span=high-low;pad=max(.006,.09*span)
        lo=math.floor((low-pad)*100)/100;hi=math.ceil((high+pad)*100)/100
        if low>=0:lo=max(0,lo)
        assert lo<=low and hi>=high
        limits[metric]=[lo,hi];ax.set_ylim(lo,hi)
        ax.set_xscale('log');ax.set_xticks(eps,[f'{e:g}' for e in eps]);ax.minorticks_off();ax.tick_params(axis='x',labelsize=6.5)
        if metric=='RepresentativeRealCoverage':title=a.representative_label
        ax.set_title(f'({chr(97+i)}) {title}',loc='left',fontsize=8.5);ax.set_xlabel('Privacy budget ε');ax.set_box_aspect(.60);ax.grid(axis='y',alpha=.2);ax.spines[['top','right']].set_visible(False)
    axes.flat[-1].axis('off');axes.flat[-1].legend(*axes.flat[0].get_legend_handles_labels(),loc='upper left',bbox_to_anchor=(0,1.08),frameon=False,fontsize=7.5)
    axes.flat[-1].text(.02,.01,'DFR: five-seed mean ± SD\nOther methods: one run per budget\nCoordinate methods: light MM2\nDFR / MTNet / MTNet+DP-OD: native roads\nFull corpus: 15,730 slots',transform=axes.flat[-1].transAxes,fontsize=7,color='#555555')
    if missing:
        axes.flat[-1].text(.02,-.10,f'Partial: {len(rows)-missing}/{len(rows)} points; gaps = pending',transform=axes.flat[-1].transAxes,fontsize=7,color='#555555')
    for ext in ['png','pdf']:fig.savefig(a.out/f'budget_current.{ext}',dpi=300)
    plt.close(fig)
    with (a.out/'plot_data.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    assert list(csv.DictReader((a.out/'plot_data.csv').open(encoding='utf-8-sig')))==rows
    font=ImageFont.truetype(str(Path(matplotlib.get_data_path())/'fonts/ttf/DejaVuSans.ttf'),32)
    for left,name,label in [(s/'budget_current.png','compare_github.png','GitHub original'),(BASE/'sources/previous/budget_k5.png','compare_previous.png','Previous 5-route figure')]:
        l=Image.open(left).convert('RGB');r=Image.open(a.out/'budget_current.png').convert('RGB')
        canvas=Image.new('RGB',(l.width+r.width,max(l.height,r.height)+90),'white');canvas.paste(l,(0,90));canvas.paste(r,(l.width,90));d=ImageDraw.Draw(canvas);d.text((20,20),label,font=font,fill='black');d.text((l.width+20,20),'Current task; all source-table values preserved',font=font,fill='black');canvas.save(a.out/name)
    Image.open(a.out/'budget_current.png').convert('L').save(a.out/'grayscale.png')
    audit=dict(status='PASS',values_unchanged=len(rows),methods=methods,original_redraw_cells=77,github_commit='eb9b563dbc371795dc84905de4e9e2f8c05ee146',input_sha256=sha(a.data),axis_limits=limits,outputs={f.name:sha(f) for f in a.out.iterdir() if f.is_file()})
    audit.update(status='PARTIAL' if missing else 'PASS',values_unchanged=len(rows)-missing,missing_values=missing,missing_policy='explicit gaps; no interpolation or zero filling')
    (a.out/'manifest.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print(f'{audit["status"]}: {len(rows)-missing} unchanged values; {missing} pending; all available mean±SD intervals visible.')
if __name__=='__main__':
    start=time.perf_counter();code=0
    try:main()
    except BaseException:code=1;raise
    finally:
        # Operator command receipts are maintained separately; do not assume a docs directory.
        print(json.dumps(dict(internal_argv=sys.argv,exit_code=code,seconds=time.perf_counter()-start)))
