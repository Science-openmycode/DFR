"""Prevent retired tasks, hidden predictors and missing new package assets."""
import ast
from pathlib import Path
import re
from tools.package_delivery import collect_files

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parents[1]


def test_package_contains_new_task_runtime_and_plot_assets():
    files={p.relative_to(ROOT).as_posix() for p in collect_files(ROOT)}
    required={'evaluate_applications.py','configure_applications.py','prepare_application_inputs.py',
              'plot_applications.py','evaluation/applications/engine.py','evaluation/applications/framework.py',
              'reference_results/matrix/spec_framework.json','configs/application_tasks/beijing_questions.json',
              'configs/application_tasks/beijing_region.json','reference_results/applications/results.csv'}
    assert required <= files
    assert not any('previous_code/' in p for p in files)
    assert not any(p.endswith(('evaluate_tstr.py','run_tstr_experiment.py','downstream_full_protocol.py')) for p in files)


def test_no_hidden_predictive_tasks_in_coordinate_scoring():
    retired={'destination_tstr_metrics','destination_conditioned_next_region_metrics',
             'grid_route_choice_metrics','continuation_metrics','retrieval_metrics'}
    for relative in ['evaluation/evaluation/evaluate_all.py',
                     'reproduction/beijing/legacy/evaluation/evaluation/evaluate_all.py']:
        s=(REPO/relative).read_text(encoding='utf-8-sig')
        tree=ast.parse(s)
        assert 'downstream_full_protocol' not in s
        assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
                       and n.func.attr in retired for n in ast.walk(tree))
        assert 'distribution_diagnostics' in s


def test_main_and_section_local_links_exist():
    for p in [REPO/'README.md',REPO/'README_CN.md',*(REPO/'分节命令').glob('*.md')]:
        for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8-sig')):
            if target.startswith(('http:','https:','#','mailto:')):
                continue
            assert (p.parent/target.split('#')[0]).exists(),(p,target)


def test_retired_reference_cannot_fill_new_figure():
    import pytest
    from evaluation.applications.visualization import organize_columns
    with pytest.raises(ValueError,match='Retired prediction reference'):
        organize_columns([],['Real-train [TSTR reference]'],['BTF'])
