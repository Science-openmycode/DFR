"""The root all-figure workflow includes the replacement applications."""
import importlib.util
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]


def module():
    spec=importlib.util.spec_from_file_location('root_current_plot_dispatch',ROOT/'plotting/regenerate_figures.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def test_all_figures_runs_applications_in_the_replaced_slot(tmp_path,monkeypatch):
    mod=module();called=[]
    names=['evidence_chain','framework','privacy','profile','mr','ablation','applications','structure']
    for name in names:
        monkeypatch.setattr(mod,'plot_'+name,lambda n=name:called.append(n))
    monkeypatch.setattr(sys,'argv',['regenerate_figures.py','--figure','all','--out-dir',str(tmp_path/'figures')])
    mod.main()
    assert called==names


def test_explicit_new_batch_never_falls_back_to_packaged_answers(tmp_path,monkeypatch):
    mod=module();monkeypatch.setattr(mod,'DATA_ROOT',tmp_path)
    with pytest.raises(ValueError,match='no new-batch fallback'):
        mod.plot_applications()
