"""The new tasks replace the old section and implementations, not coexist."""
from pathlib import Path
import ast
import re

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]


def test_retired_entry_points_are_absent():
    for name in ['evaluate_tstr.py','experiments/tstr.py','prepare_remote_tstr.py',
                 'legacy/evaluation/run_tstr_experiment.py',
                 'legacy/evaluation/pipeline/evaluate_generic_mobility_tasks.py',
                 'plotting/plot_current_frozen.py']:
        assert not (ROOT/name).exists(),name
    assert not (REPO/'evaluation/run_tstr_experiment.py').exists()


def test_new_tasks_occupy_original_downstream_position():
    section=(REPO/'分节命令/第05节_四项下游任务与图件.md').read_text(encoding='utf-8')
    for name in ['README.md','README_CN.md']:
        s=(REPO/name).read_text(encoding='utf-8')
        assert s.index('id="sec-04"') < s.index('id="sec-05"') < s.index('id="sec-06"')
        assert section.replace('](../reproduction/', '](reproduction/') in s
        assert 'sec-08-2' not in s and 'evaluate_tstr.py' not in s
        assert '严格TSTR' not in s
        for target in re.findall(r'\]\((分节命令/[^)]+)\)',s):
            assert (REPO/target.split('#')[0]).exists(),target


def test_no_old_task_dispatch_in_active_modules():
    for name in ['experiments/_plans.py','experiments/_table_jobs.py',
                 'experiments/_table_catalog.py','tools/collect_frozen_matrix.py',
                 'evaluation/audit_v2_runner.py','plotting/render_verified_matrix.py']:
        s=(ROOT/name).read_text(encoding='utf-8')
        ast.parse(s)
        assert 'run_tstr_experiment' not in s
        for metric in ['NextCellHit1','DestinationHit5','RoadContinuationHit1','RouteRetrievalNDCG5']:
            assert metric not in s


def test_shared_provenance_has_no_task_evaluator_dependency():
    s=(ROOT/'legacy/evaluation/release_provenance.py').read_text(encoding='utf-8')
    assert 'def base_release_hash' in s and 'def aggregate' not in s
    s=(ROOT/'legacy/evaluation/experiment_contract.py').read_text(encoding='utf-8')
    assert 'from release_provenance import base_release_hash' in s
    assert 'from run_tstr_experiment' not in s
