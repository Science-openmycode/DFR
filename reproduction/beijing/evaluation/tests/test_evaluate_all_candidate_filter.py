from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from run import _evaluation_candidates


def test_intermediate_mm2_chunks_are_not_evaluation_cells(tmp_path: Path) -> None:
    complete = tmp_path / "SPRT" / "MM2-MDP" / "synthetic_routes.pkl.gz"
    chunk = tmp_path / "SPRT" / "MM2-MDP" / "mm2_batches" / "000000_002048" / "run" / "synthetic_routes.pkl.gz"
    complete.parent.mkdir(parents=True)
    chunk.parent.mkdir(parents=True)
    complete.write_bytes(b"x")
    chunk.write_bytes(b"x")
    candidates = _evaluation_candidates(tmp_path)
    assert candidates == [complete]
