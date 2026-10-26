import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT=Path(__file__).parents[2]
sys.path.insert(0,str(ROOT))
from tools.owned_worker_memory_guard import OwnedWorkerMemoryGuard


def test_low_memory_terminates_only_owned_descendants(tmp_path,monkeypatch):
    terminated=[]
    child=SimpleNamespace(pid=51,memory_info=lambda:SimpleNamespace(private=2**30,rss=2**30),terminate=lambda:terminated.append(51))
    parent=SimpleNamespace(children=lambda recursive:[child])
    fake=SimpleNamespace(Process=lambda:parent,virtual_memory=lambda:SimpleNamespace(available=2**30),NoSuchProcess=ProcessLookupError,AccessDenied=PermissionError)
    monkeypatch.setitem(sys.modules,'psutil',fake)
    report=tmp_path/'memory.json'
    guard=OwnedWorkerMemoryGuard(2,report);guard.watch()
    assert terminated==[51]
    assert guard.exceeded.is_set()
    assert json.loads(report.read_text())['terminated_owned_pids']==[51]


def test_sufficient_memory_does_not_terminate(tmp_path,monkeypatch):
    guard=OwnedWorkerMemoryGuard(2,tmp_path/'memory.json')
    def sample():
        guard.stopped.set()
        return SimpleNamespace(available=4*2**30)
    fake=SimpleNamespace(Process=lambda:SimpleNamespace(children=lambda recursive:[]),virtual_memory=sample,NoSuchProcess=ProcessLookupError,AccessDenied=PermissionError)
    monkeypatch.setitem(sys.modules,'psutil',fake)
    guard.watch()
    assert not guard.exceeded.is_set()
    assert guard.stats['minimum_available_gib']==4
