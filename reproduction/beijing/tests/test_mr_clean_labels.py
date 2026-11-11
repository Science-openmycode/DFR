import importlib.util
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def test_remove_only_figure_explanations_preserving_cells_and_axis_labels(monkeypatch):
    directory=Path(__file__).resolve().parents[1]/'plotting'
    monkeypatch.syspath_prepend(str(directory))
    spec=importlib.util.spec_from_file_location('mr_clean_labels_test',directory/'render_mr.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    fig,ax=plt.subplots()
    fig.suptitle('Title');fig.text(.5,.9,'Subtitle');fig.text(.5,.05,'Footer')
    ax.set_xticks([0],['DFR']);ax.set_yticks([0],['BTF'])
    ax.text(0,0,'0.377');ax.text(1.01,0,'Task group')
    limits=(ax.get_xlim(),ax.get_ylim())
    module.remove_explanatory_text(fig)
    assert not fig.texts
    assert [t.get_text() for t in ax.texts]==['0.377','Task group']
    assert ax.get_xticklabels()[0].get_text()=='DFR'
    assert ax.get_yticklabels()[0].get_text()=='BTF'
    assert (ax.get_xlim(),ax.get_ylim())==limits
    plt.close(fig)
