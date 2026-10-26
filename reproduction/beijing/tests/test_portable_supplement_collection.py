import json
from pathlib import Path
import pytest
from tools.collect_portable_sweeps import aggregate

ROOT=Path(__file__).resolve().parents[1]


def test_budget_aggregator_matches_all_saved_values():
    saved=json.loads((ROOT/'reference_results/budget/summary.json').read_text(encoding='utf-8'))
    result=aggregate(saved['rows'],'epsilon')
    assert result==saved['aggregates']
    assert len(result)==76*7


def test_duplicate_seed_rejected():
    rows=[dict(stage='roads',metric='BTF',epsilon=1.4,seed=42,value=.5) for _ in range(5)]
    with pytest.raises(ValueError):aggregate(rows,'epsilon')


def test_missing_not_zero():
    rows=[dict(stage='roads',metric='BTF',k=24,seed=i,value=None) for i in range(5)]
    result=aggregate(rows,'k')[0]
    assert result['n']==0 and result['mean'] is None and result['sd'] is None
