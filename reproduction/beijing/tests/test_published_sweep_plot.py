"""Plot-only regression tests: saved scores are never recomputed or adjusted."""
import json
from pathlib import Path
import pytest
from plotting.render_current_sweeps import PANELS, application_limits, values

ROOT = Path(__file__).resolve().parents[1]


def test_published_scores_and_plot_tables_agree():
    base = ROOT/'reference_results/sensitivity_current'
    apps = json.loads((base/'summary.json').read_text(encoding='utf-8'))
    assert apps['cells'] == 65 and len(apps['rows']) == 260
    assert len(PANELS) == 11
    count = 0
    for kind, source in [('k', ROOT/'reference_results/k/all_metrics.json'),
                         ('budget', ROOT/'reference_results/budget/summary.json')]:
        data = values(source, base/'summary.json', kind)
        for r in json.loads((base/f'figures/{kind}/plot_data.json').read_text(encoding='utf-8')):
            assert r['values'] == [data[r['x'], seed, r['stage'], r['metric']] for seed in range(20260719, 20260724)]
            count += len(r['values'])
    assert count == 715


def test_application_windows_do_not_clip_other_data():
    assert application_limits('IncomingExitDistributionOverlap',
        [dict(values=[.62, .7], mean=.66, sd=.04)]) == (.6, .75)
    lo, hi = application_limits('IncomingExitDistributionOverlap',
        [dict(values=[.5, .9], mean=.7, sd=.25)])
    assert lo <= .45 and hi >= .95


def test_conflicting_application_scores_are_rejected(tmp_path):
    source = tmp_path/'source.json'; apps = tmp_path/'apps.json'
    metric = PANELS[-1][1]
    source.write_text(json.dumps(dict(rows=[dict(epsilon=1.4, seed=20260719,
        stage='applications', metric=metric, value=.1)])))
    apps.write_text(json.dumps(dict(status='COMPLETE', rows=[dict(kind='budget',
        value=1.4, seed=20260719, metric=metric, score=.2)])))
    with pytest.raises(ValueError, match='differs'):
        values(source, apps, 'budget')
