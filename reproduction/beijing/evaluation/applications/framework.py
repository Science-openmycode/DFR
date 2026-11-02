"""Canonical final framework renderer shared by README and public plot entry points."""
import json
from pathlib import Path
from .visualization import organize_columns, matrix, digest


def prepare_cells(cells, spec):
    if spec.get('view')!='application_framework':raise ValueError('Require application framework specification')
    methods=list(dict.fromkeys(c['row'] for c in cells))
    result,methods=organize_columns(cells,methods,spec['columns'])
    missing=[(c['row'],c['metric']) for c in result if c['status']=='MISSING']
    if missing:raise ValueError('Missing applicable scores; not a complete framework: '+str(missing))
    by={(c['row'],c['metric']):c for c in result}
    expected={(m,k) for m in methods for k in spec['columns']}
    if set(by)!=expected or len(by)!=len(result):raise ValueError('Incomplete or duplicate framework cells')
    return result,methods


def render(cells,spec,out,population=None,previous=None,github=None,pair=None):
    cells,methods=prepare_cells(cells,spec)
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    matrix(cells,methods,spec['columns'],out)
    (out/'cells.json').write_text(json.dumps(cells,ensure_ascii=False,indent=2),encoding='utf-8')
    if previous and pair:
        source=Path(previous)/'framework_matrix_transposed.png'
        if source.is_file():pair(source,out/'framework_matrix_transposed.png',out/'previous_vs_current.png',('PREVIOUS VERIFIED FIGURE','README MAIN ENTRY - SAME FIGURE CONTRACT'))
    if github and pair:
        pair(github,out/'framework_matrix_transposed.png',out/'github_vs_current.png',('GITHUB HISTORICAL ORIGINAL - DIFFERENT FIGURE','CURRENT APPLICATION FRAMEWORK'))
    return dict(view='application_framework',rows=spec['columns'],columns=methods,
        shape=[len(spec['columns']),len(methods)],missing_applicable=0,no_metrics_recomputed=True,
        reference_policy='Real: geometry reference for seven base metrics, application reference for four tasks; per-cell provenance retained',
        files={p.name:digest(p) for p in out.iterdir() if p.is_file()})
