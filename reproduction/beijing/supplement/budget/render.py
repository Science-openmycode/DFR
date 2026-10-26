"""Style-only rendering. Never generate, reroute, evaluate, or change metrics."""
import hashlib
import json
import math
import statistics
import textwrap
import time
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.ticker import MaxNLocator, NullLocator, ScalarFormatter
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT/'reference_results/budget/summary.json'
OUT = HERE/'output_v5'
COLORS = ['#0072B2','#D55E00','#009E73','#CC79A7','#E69F00','#56B4E9','#009E73','#D55E00']
PRETTY = {
 'grid_density_jsd':'Grid JSD', 'trip_error':'Trip error', 'path_length_jsd':'Length JSD',
 'DirValidRoadObject':'Native validity', 'RC-CPC':'RC-CPC', 'RC-NDCG':'RC-NDCG',
 'NextRoadAcc':'NextRoadAcc', 'NextRoadNLL':'NextRoadNLL',
 'A1_count_jsd_mean':'Count JSD','A1_range_are_nonzero':'Range ARE','A1_range_smape':'Range SMAPE',
 'B1_dest16_macro_f1':'Destination F1 (16)','B1_dest16_top1':'Destination top-1 (16)',
 'B1_dest16_top5':'Destination top-5 (16)','B1_dest8_macro_f1':'Destination F1 (8)',
 'B1_dest8_top1':'Destination top-1 (8)','B1_dest8_top5':'Destination top-5 (8)',
 'B2_grid_route_best5_transition_f1':'Best-5 transition F1','B2_grid_route_mrr':'Grid-route MRR',
 'B2_grid_route_od_coverage':'Grid-route OD coverage','B2_grid_route_top1_hit':'Grid-route top-1',
 'B2_grid_route_top1_transition_f1':'Top-1 transition F1','B2_grid_route_top3_hit':'Grid-route top-3',
 'B2_grid_route_top5_hit':'Grid-route top-5','B2_next_region_accuracy':'Next-region accuracy',
 'B2_next_region_nll':'Next-region NLL','conditional_nn_dtw_km':'Conditional DTW (km)',
 'conditional_nn_frechet_km':'Conditional Frechet (km)',
 'coordinate_projection_directed_road_validity':'Projected direction validity',
 'coordinate_projection_route_compatible_yield':'Projected route yield',
 'CoordinatePairValidity':'Coordinate-pair validity','directed_road_validity':'Road direction validity',
 'OD_jsd':'OD JSD','OD_ndcg20':'OD NDCG@20','OD_spearman':'OD Spearman',
 'OD_top20_overlap':'OD top-20 overlap','road_route_valid':'Road-route validity',
 'road_segment_jsd':'Road-segment JSD','route_compatible_yield':'Route-compatible yield',
 'witness_valid':'Witness validity', 'conditional_next_road_accuracy':'Conditional NextRoadAcc',
 'conditional_next_road_nll':'Conditional NextRoadNLL','conditional_rc_ndcg':'Conditional RC-NDCG',
 'conditional_road_choice_cpc':'Conditional RC-CPC',
}
MAIN = [('coordinate_scores',m) for m in ['grid_density_jsd','trip_error','path_length_jsd','DirValidRoadObject']]+[
 ('road_scores','RC-CPC'),('road_tasks','RC-NDCG'),('road_tasks','NextRoadAcc'),('road_tasks','NextRoadNLL')]

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def title(key):
    m=key[1]
    label=PRETTY.get(m, __import__('re').sub(r'(?<=[a-z])(?=[A-Z])',' ',m))
    lower=any(t in m.lower() for t in ['jsd','error','smape','are_nonzero','nll','dtw','frechet'])
    # Retention is a ratio, not intrinsically "higher is better".
    arrow='' if 'retention' in m.lower() else (' ↓' if lower else ' ↑')
    return label+arrow

def draw(data,keys):
    rows=math.ceil(len(keys)/4)
    fig,axes=plt.subplots(rows,4,figsize=(7.2,1.65*rows+.30),squeeze=False)
    for i,(ax,key) in enumerate(zip(axes.flat,keys)):
        items=sorted([r for r in data['aggregates'] if (r['stage'],r['metric'])==key],key=lambda r:r['epsilon'])
        assert len(items)==7
        x=[r['epsilon'] for r in items]; y=[float('nan') if r['mean'] is None else r['mean'] for r in items]
        sd=[float('nan') if r['sd'] is None else r['sd'] for r in items]
        c=COLORS[i%8]
        ax.fill_between(x,[a-b for a,b in zip(y,sd)],[a+b for a,b in zip(y,sd)],color=c,alpha=.18,lw=0)
        for r in data['rows']:
            if (r['stage'],r['metric'])==key and r['value'] is not None:
                ax.plot(r['epsilon'],r['value'],'.',color=c,alpha=.28,ms=2,zorder=2)
        ax.plot(x,y,'o-',color=c,lw=1.45,ms=3.0,zorder=3)
        ax.axvline(1.4,color='#6B7280',lw=.65,ls='--',zorder=1)
        ax.set_xscale('log'); ax.set_xlim(.175,3.4)
        ax.set_xticks([.2,.7,1.4,3],['0.2','0.7','1.4','3']); ax.xaxis.set_minor_locator(NullLocator())
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4)); ax.yaxis.set_major_formatter(ScalarFormatter(useOffset=False))
        ax.grid(axis='y',color='#DEDEDE',lw=.45); ax.set_axisbelow(True)
        label='\n'.join(textwrap.wrap(title(key),18))
        ax.set_title(f'({chr(97+i)}) '+label,loc='left',fontweight='bold',fontsize=7.3,pad=5)
        ax.set_xlabel(r'$\epsilon$' if i//4==rows-1 else '',labelpad=1)
        ax.tick_params(length=2.5,width=.65,pad=2)
        ax.margins(y=.14)
        if not any(r['mean'] is not None for r in items):
            ax.text(.5,.5,'NA',transform=ax.transAxes,ha='center',color='#666666',fontsize=11)
            ax.set_yticks([])
        elif any(r['n']<5 for r in items):
            ax.text(.04,.04,'Incomplete n; see data',transform=ax.transAxes,fontsize=5.5)
    for ax in list(axes.flat)[len(keys):]: ax.set_visible(False)
    fig.subplots_adjust(left=.065,right=.995,bottom=.38/fig.get_figheight(),top=1-.43/fig.get_figheight(),wspace=.40,hspace=.57)
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer()
    for ax in list(axes.flat)[:len(keys)]:
        text=ax._left_title
        while text.get_window_extent(renderer).width > ax.bbox.width+3 and text.get_fontsize()>6.1:
            text.set_fontsize(text.get_fontsize()-.2)
            fig.canvas.draw()
        box=text.get_window_extent(renderer)
        assert box.y1 < fig.bbox.y1 and box.x1 < fig.bbox.x1, (text.get_text(),box)
    return fig

def pair(left,right,out,left_title,right_title):
    ims=[Image.open(p).convert('RGB') for p in [left,right]]
    w=2100; h=1050; canvas=Image.new('RGB',(w*2,h+65),'white');d=ImageDraw.Draw(canvas)
    for i,(im,label) in enumerate(zip(ims,[left_title,right_title])):
        im.thumbnail((w-30,h-20)); canvas.paste(im,(i*w+(w-im.width)//2,65+(h-im.height)//2))
        d.text((i*w+25,22),label,fill='black',font_size=25)
    canvas.save(out)

def main():
    started=time.perf_counter()
    if OUT.exists(): raise FileExistsError(OUT)
    data=json.loads(SOURCE.read_text(encoding='utf-8'))
    assert data['runs']==35 and data['seeds_per_epsilon']==5
    keys=sorted({(r['stage'],r['metric']) for r in data['rows']})
    assert len(keys)==76 and set(MAIN)<=set(keys)
    checks=0
    for agg in data['aggregates']:
        vals=[r['value'] for r in data['rows'] if all(r[k]==agg[k] for k in ['stage','metric','epsilon']) and r['value'] is not None]
        assert len(vals)==agg['n']
        if vals:
            assert math.isclose(statistics.mean(vals),agg['mean'],abs_tol=1e-13)
            if len(vals)>1: assert math.isclose(statistics.stdev(vals),agg['sd'],abs_tol=1e-13)
        else: assert agg['mean'] is None and agg['sd'] is None
        checks+=1
    OUT.mkdir(parents=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':7.3,'axes.labelsize':8,
        'xtick.labelsize':7,'ytick.labelsize':7,'axes.linewidth':.7,
        'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42,'svg.fonttype':'none'})
    fig=draw(data,MAIN)
    for ext in ['png','pdf','svg']: fig.savefig(OUT/f'budget_main.{ext}',dpi=400)
    plt.close(fig)
    groups=[]
    with PdfPages(OUT/'budget_all_metrics.pdf') as pdf:
        for stage in ['road_scores','physical','road_tasks','coordinate_scores']:
            stagekeys=[k for k in keys if k[0]==stage]
            for offset in range(0,len(stagekeys),8):
                group=stagekeys[offset:offset+8]; idx=len(groups)+1
                fig=draw(data,group); pdf.savefig(fig)
                fig.savefig(OUT/f'appendix_{idx:02}.png',dpi=300);plt.close(fig)
                groups.append({'page':idx,'stage':stage,'keys':group})
    old=ROOT/'reference_results/budget/previous'
    for i in range(1,8):
        oldkeys=keys[(i-1)*12:i*12]
        fig=draw(data,oldkeys)
        path=OUT/f'old_page_{i:02}_restyled.png';fig.savefig(path,dpi=300);plt.close(fig)
        pair(old/f'budget35_page_{i:02}.png',path,OUT/f'before_after_{i:02}.png',
             f'Previous diagnostic atlas / page {i}',f'Paper style / identical metrics / page {i}')
    paper=ROOT/'reference_results/budget/paper_budget_reference.png'
    pair(paper,OUT/'budget_main.png',OUT/'paper_style_comparison.png','Paper original / historical GSRT data','New Beijing DFR / 35 runs / sample SD')
    pair(HERE/'github_readme_profile.png',OUT/'budget_main.png',OUT/'github_style_reference.png',
         'GitHub README original / historical profile, NOT budget data','New DFR budget figure / style reference ONLY')
    Image.open(OUT/'budget_main.png').convert('L').save(OUT/'budget_main_grayscale.png')
    caption=('Beijing DFR privacy-budget sensitivity. Each point is the mean of five independent research seeds; '
             'shading is sample standard deviation, NOT a confidence interval. The dashed line marks requested epsilon=1.4. '
             'Native validity is DirValidRoadObject, NOT the undefined witness_valid field. '
             'Full-corpus retrospective utility, not strict train-only TSTR. Four generation outer-exit anomalies '
             'are retained in the source summary. No historical GSRT values or intervals are reused.')
    (OUT/'caption.txt').write_text(caption,encoding='utf-8')
    files={p.name:sha(p) for p in OUT.iterdir() if p.is_file()}
    report={'input_sha256':sha(SOURCE),'source_sha256':sha(__file__),'aggregate_cells_verified':checks,
        'all_76_metrics_retained':True,'main_keys':MAIN,'appendix_pages':groups,'caption':caption,
        'github_commit':'87be8ec856990cdec16cb4ccfb5ccc2a2c87b039',
        'github_path':'experiment_results/published_figures/01_overall_profile.png',
        'github_original_sha256':sha(HERE/'github_readme_profile.png'),
        'paper_budget_reference_sha256':sha(paper),'historical_budget_renderer_replayed':False,
        'historical_budget_renderer_gap':'Source function not found in paper source; visual style reference only',
        'old_figure_data_unchanged':True,'new_experiments_executed':False,
        'render_seconds_before_manifest':time.perf_counter()-started,'outputs':files}
    (OUT/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'verified_aggregate_cells':checks,'metric_panels':len(keys),'appendix_pages':len(groups),'output':str(OUT)}))

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=SOURCE)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();SOURCE=args.source;OUT=args.out
    main()
