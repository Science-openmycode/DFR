from __future__ import annotations

import gzip
import pickle
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import align_metric_cache


def dump(path: Path, value: dict) -> None:
    with gzip.open(path, "wb") as handle:
        pickle.dump(value, handle)


def test_aligns_labels_by_common_edge_ids_and_recomputes_outdegree(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared.pkl.gz"
    legacy = tmp_path / "legacy.pkl.gz"
    out = tmp_path / "aligned.pkl.gz"
    dump(prepared, {"edge_nodes": {10: (100, 101), 11: (101, 102)}})
    dump(legacy, {
        "edge_nodes": {10: (1, 2), 11: (2, 3)},
        "labels24": {1: 4, 2: 5, 3: 6},
        "labels96": {1: 40, 2: 41, 3: 42},
        "labels384": {1: 200, 2: 201, 3: 202},
        "portals": [1, 3],
        "outdegree": {1: 1, 2: 1, 3: 0},
    })
    manifest = align_metric_cache.align(prepared, legacy, out)
    result = align_metric_cache.load(out)
    assert result["labels96"] == {100: 40, 101: 41, 102: 42}
    assert result["outdegree"] == {100: 1, 101: 1, 102: 0}
    assert result["portals"] == [100, 102]
    assert manifest["common_edge_count"] == 2
    assert manifest["node_conflicts"] == 0


def test_rejects_inconsistent_node_mapping(tmp_path: Path) -> None:
    prepared = tmp_path / "prepared.pkl.gz"
    legacy = tmp_path / "legacy.pkl.gz"
    out = tmp_path / "aligned.pkl.gz"
    dump(prepared, {"edge_nodes": {10: (100, 101), 11: (100, 102)}})
    dump(legacy, {
        "edge_nodes": {10: (1, 2), 11: (3, 4)},
        "labels24": {1: 0, 2: 0, 3: 0, 4: 0},
        "labels96": {1: 0, 2: 0, 3: 0, 4: 0},
        "labels384": {1: 0, 2: 0, 3: 0, 4: 0},
        "portals": [],
    })
    with pytest.raises(ValueError, match="inconsistent node mapping"):
        align_metric_cache.align(prepared, legacy, out)

