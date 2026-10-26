import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "preprocess") not in sys.path:
    sys.path.insert(0, str(ROOT / "preprocess"))

from canonical_schema import load_rows  # noqa: E402


class GeolifeDirectoryTests(unittest.TestCase):
    def test_plt_directory_is_canonicalized(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "Data" / "000"
            root.mkdir(parents=True)
            (root / "Trajectory.plt").write_text(
                "Geolife trajectory\nWGS 84\nAltitude is in Feet\nReserved 3\nReserved 4\n0\n"
                "39.90,116.30,0,10,0,2008-10-23,02:53:04\n"
                "39.91,116.31,0,11,0,2008-10-23,02:54:04\n",
                encoding="utf-8",
            )
            rows = load_rows(Path(temp) / "Data")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0]["trajectory_id"], "000/Trajectory")
            self.assertEqual(rows[0][0]["timestamp"], "2008-10-23 02:53:04")
            self.assertEqual(rows[0][1]["sequence_index"], 1)


if __name__ == "__main__":
    unittest.main()
