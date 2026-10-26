from __future__ import annotations

import gzip
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import compute_edge_route_metrics


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wb") as handle:
        pickle.dump(value, handle)


def test_scores_edge_id_cpath_without_merging_node_namespaces(tmp_path: Path) -> None:
    cache = {
        "classification": "PUBLIC_METRIC_CACHE",
        "edge_nodes": {1: (10, 11), 2: (11, 12), 3: (10, 12)},
        "outdegree": {10: 2, 11: 1, 12: 0},
        "labels24": {10: 0, 11: 1, 12: 2},
        "labels96": {10: 0, 11: 1, 12: 2},
        "labels384": {10: 0, 11: 1, 12: 2},
    }
    cache_path = tmp_path / "metric_cache.pkl.gz"
    dump(cache_path, cache)
    real_path = tmp_path / "Real.pkl.gz"
    syn_path = tmp_path / "synthetic_routes.pkl.gz"
    dump(real_path, [{"accepted": True, "cpath": [1, 2]}])
    dump(syn_path, [{"accepted": True, "cpath": [1, 2]}])
    result = compute_edge_route_metrics.score_pair(real_path, syn_path, cache_path)
    assert result["EdgeCPC"] == 1.0
    assert result["TurnCPC"] == 1.0
    assert result["RoadYield"] == 1.0

