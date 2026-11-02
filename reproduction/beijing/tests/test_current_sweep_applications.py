import json
from pathlib import Path
import pytest
from plotting.render_current_sweeps import PANELS, values, render, application_limits
from tools.collect_sweep_applications import METRICS
from tools.collect_portable_sweeps import collect


def test_current_panels_replace_predictions():
    names = [p[1] for p in PANELS]
    assert len(names) == 11 and len(set(names)) == 11
    assert names[-4:] == list(METRICS)
    assert not any('B1_' in n or 'B2_' in n or 'NextCell' in n for n in names)


def test_zoomed_application_limits_show_data_and_uncertainty():
    metric = 'IncomingExitDistributionOverlap'
    assert application_limits(metric, [dict(values=[.62,.70],mean=.66,sd=.04)]) == (.60,.75)
    lo, hi = application_limits(metric, [dict(values=[.5,.9],mean=.7,sd=.25)])
    assert lo <= .45 and hi >= .95


@pytest.mark.parametrize('kind', ['k', 'budget'])
def test_summary_cannot_silently_skip_new_tasks(tmp_path, kind):
    with pytest.raises(ValueError, match='applications-plan'):
        collect(kind, tmp_path/'missing_plan.json', tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_figure_rejects_conflicting_application_scores(tmp_path):
    s = tmp_path/'source.json'; a = tmp_path/'apps.json'
    s.write_text(json.dumps({'rows': [dict(epsilon=1.4, seed=20260719,
        stage='applications', metric=METRICS[0], value=.1)]}))
    a.write_text(json.dumps(dict(status='COMPLETE', rows=[dict(kind='budget', value=1.4,
        seed=20260719, metric=METRICS[0], score=.2)])))
    with pytest.raises(ValueError, match='differs'):
        values(s, a, 'budget')


def test_figure_does_not_fill_missing_seeds(tmp_path):
    s = tmp_path/'source.json'; a = tmp_path/'apps.json'
    s.write_text(json.dumps({'rows': []}))
    a.write_text(json.dumps(dict(status='COMPLETE', rows=[])))
    with pytest.raises(KeyError):
        render('k', s, a, tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_historical_k_metrics_retained_exactly(tmp_path):
    source = Path(__file__).resolve().parents[1]/'reference_results/k/all_metrics.json'
    a = tmp_path/'apps.json'; a.write_text(json.dumps(dict(status='COMPLETE', rows=[])))
    actual = values(source, a, 'k')
    saved = json.loads(source.read_text(encoding='utf-8'))
    for r in saved:
        if not r['diagnostic']:
            for stage in ('road_scores', 'coordinate_scores'):
                for key, value in r[stage].items():
                    assert actual[r['k'], r['seed'], stage, key] == value
