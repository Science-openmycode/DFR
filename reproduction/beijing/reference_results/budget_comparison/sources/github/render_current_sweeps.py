"""Current seven distribution/structure metrics plus four real-question tasks.

Read-only plotting. Supports historical saved summaries without rerunning
generation and current collect_portable_sweeps summaries. Never imputes scores.
"""
import argparse
import hashlib
import json
import math
import statistics
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

PANELS = [('coordinate_scores', 'grid_density_jsd', 'Grid JSD ↓'),
          ('coordinate_scores', 'trip_error', 'Trip error ↓'),
          ('coordinate_scores', 'path_length_jsd', 'Length JSD ↓'),
          ('road_scores', 'RoadYield', 'Road yield ↑'),
          ('road_scores', 'BTF', 'BTF ↑'),
          ('road_scores', 'FamilyCPC', 'Family CPC ↑'),
          ('road_scores', 'ODPF384', 'ODPF384 ↑'),
          ('applications', 'MFPOrderedRouteOverlap', 'Frequent routes ↑'),
          ('applications', 'RepresentativeRealCoverage', 'Representative coverage ↑'),
          ('applications', 'SelectedRoadMarginalOverlap', 'Road source / destination ↑'),
          ('applications', 'IncomingExitDistributionOverlap', 'Intersection turns ↑')]

APPLICATION_YLIMS = {
    'MFPOrderedRouteOverlap': (.10, .35),
    'RepresentativeRealCoverage': (.65, .85),
    'SelectedRoadMarginalOverlap': (.35, .55),
    'IncomingExitDistributionOverlap': (.60, .75),
}


def application_limits(metric, groups):
    """Keep comparable display windows without clipping future cities/data."""
    lo, hi = APPLICATION_YLIMS[metric]
    lower = [min(min(r['values']), r['mean']-r['sd']) for r in groups]
    upper = [max(max(r['values']), r['mean']+r['sd']) for r in groups]
    lo = min(lo, math.floor(min(lower)/.05)*.05)
    hi = max(hi, math.ceil(max(upper)/.05)*.05)
    return lo, hi


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def values(source, applications, kind):
    data = json.loads(source.read_text(encoding='utf-8')); result = {}
    if isinstance(data, list):
        for r in data:
            if r.get('diagnostic'):
                continue
            for stage in ('coordinate_scores', 'road_scores'):
                for metric, value in r[stage].items():
                    result[(r['k'], r['seed'], stage, metric)] = value
    else:
        axis = 'epsilon' if kind == 'budget' else 'k'
        for r in data['rows']:
            key = (r[axis], r['seed'], r['stage'], r['metric'])
            if key in result:
                raise ValueError('Duplicate observation')
            result[key] = r['value']
    apps = json.loads(applications.read_text(encoding='utf-8'))
    if apps['status'] != 'COMPLETE':
        raise ValueError('Unverified application summary')
    for r in apps['rows']:
        if r['kind'] == kind:
            key = (r['value'], r['seed'], 'applications', r['metric'])
            if key in result and result[key] != r['score']:
                raise ValueError('Application score differs between summaries')
            result[key] = r['score']
    return result


def render(kind, source, applications, out):
    data = values(source, applications, kind)
    xs = [24, 48, 96, 192, 384, 768] if kind == 'k' else [.2, .4, .7, 1, 1.4, 2, 3]
    seeds = range(20260719, 20260724); table = []
    for stage, metric, title in PANELS:
        for x in xs:
            vals = [data[(x, seed, stage, metric)] for seed in seeds]
            if any(v is None for v in vals):
                raise ValueError('Missing metric: '+metric)
            table.append(dict(stage=stage, metric=metric, x=x, mean=statistics.mean(vals),
                              sd=statistics.stdev(vals), n=5, values=vals))
    out.mkdir(parents=True, exist_ok=False)
    plt.rcParams.update({'font.size': 8, 'font.family': 'DejaVu Sans', 'pdf.fonttype': 42})
    fig, axes = plt.subplots(3, 4, figsize=(13, 6.4), layout='constrained')
    axis_limits = {}
    for i, (ax, (stage, metric, title)) in enumerate(zip(axes.flat, PANELS)):
        group = [r for r in table if r['metric'] == metric and r['stage'] == stage]
        ys = [r['mean'] for r in group]; sd = [r['sd'] for r in group]
        color = '#0072B2' if stage != 'applications' else '#D55E00'
        ax.fill_between(xs, [a-b for a, b in zip(ys, sd)], [a+b for a, b in zip(ys, sd)], alpha=.17, color=color)
        for seed in seeds:
            ax.plot(xs, [data[(x, seed, stage, metric)] for x in xs], '.', ms=2.5, color=color, alpha=.28)
        ax.plot(xs, ys, 'o-', ms=3, lw=1.3, color=color)
        ax.set_xscale('log', base=2 if kind == 'k' else 10)
        ax.set_xticks(xs, [str(x) for x in xs]); ax.minorticks_off()
        ax.tick_params(axis='x', labelsize=6.5)
        ax.set_title(f'({chr(97+i)}) {title}', loc='left', fontsize=8.5)
        ax.set_xlabel('K (regions)' if kind == 'k' else 'Privacy budget ε')
        ax.set_box_aspect(.60)
        ax.grid(axis='y', alpha=.2); ax.spines[['top', 'right']].set_visible(False)
        if stage == 'applications':
            ax.set_ylim(*application_limits(metric, group))
            ax.yaxis.set_major_locator(MultipleLocator(.05))
        axis_limits[metric] = list(ax.get_ylim())
    axes.flat[-1].set_visible(False)
    for suffix in ('png', 'pdf'):
        fig.savefig(out/f'{kind}_current.{suffix}', dpi=300)
    plt.close(fig)
    (out/'plot_data.json').write_text(json.dumps(table, indent=2), encoding='utf-8')
    (out/'manifest.json').write_text(json.dumps(dict(source_sha256=digest(source), applications_sha256=digest(applications),
        renderer_sha256=digest(__file__), panels=11, aggregate_cells=len(table),
        figure_inches=[13,6.4], axes_height_over_width=.60,
        axis_limits=axis_limits, explanation_text_inside_figure=False,
        metric_groups={'base': [p[1] for p in PANELS[:7]], 'applications': [p[1] for p in PANELS[7:]]},
        unchanged_structure_values=True, old_prediction_tasks_displayed=False,
        error='sample standard deviation, n=5; not confidence intervals'), indent=2), encoding='utf-8')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kind', choices=['k', 'budget'], required=True)
    for name in ('source', 'applications', 'out'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args(); render(a.kind, a.source, a.applications, a.out)
