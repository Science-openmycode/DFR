"""Original K diagnostic arithmetic, separated from machine-specific paths."""
import numpy as np


def endpoint_diagnostics(real,labels,k,transcript,metadata):
    exact=np.zeros((2,k))
    for path in real:
        if not path:continue
        exact[0,labels[path[0][0]]]+=.5
        exact[1,labels[path[-1][1]]]+=.5
    ep=transcript['endpoint'];noisy=np.array(ep['noisy_cells'])
    if noisy.shape!=exact.shape or exact.sum()==0:raise ValueError('Wrong endpoint shape or empty real reference')
    return dict(fine_head_true_mass_fraction=float(sum(exact[role,cell] for role,cell in ep['selected_cells'])/exact.sum()),
                fine_noise_l1=float(np.abs(noisy-exact).sum()),endpoint_fallbacks=sum(ep['fallback_counts'].values()),
                public_shortest_fallbacks=metadata['tail_states'].get('single_edge_fallback',0))


def paired_summary(rows):
    keys=['OD_jsd','BTF','RC-CPC','EdgeCPC','TurnCPC','generation_seconds']
    main=[r for r in rows if not r['diagnostic']]
    baseline={r['seed']:r for r in main if r['k']==384}
    if len(baseline)!=5:raise ValueError('Require five K384 seed references')
    summary={}
    for k in (24,48,96,192,384,768):
        group=sorted((r for r in main if r['k']==k),key=lambda r:r['seed'])
        if len(group)!=5 or {r['seed'] for r in group}!=set(baseline):raise ValueError('Unpaired K seeds')
        summary[k]={m:dict(mean=float(np.mean([r[m] for r in group])),std=float(np.std([r[m] for r in group],ddof=1)),
                          paired_delta_vs384=[r[m]-baseline[r['seed']][m] for r in group]) for m in keys}
    return summary
