import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from algorithms.routers.mm2_mdp_adapter import decode_edge_ids, mm2_command, sample_points


class MM2AdapterTests(unittest.TestCase):
    def test_mm2_accepts_epsg_prefix(self):
        command = mm2_command(
            executable=Path("mm2"),
            network=Path("network"),
            tracks=Path("tracks.csv"),
            output=Path("out"),
            tracks_srs="EPSG:32650",
            network_srs="32650",
        )
        self.assertEqual(command[command.index("--tracks-srs") + 1], "32650")
        self.assertEqual(command[command.index("--network-srs") + 1], "32650")

    def test_edge_ids_are_converted_and_connected(self):
        self.assertEqual(
            decode_edge_ids("2,2,3", {1: (10, 20), 2: (20, 30)}),
            ([1, 2], "accepted"),
        )

    def test_disconnected_edges_are_not_filled(self):
        self.assertEqual(
            decode_edge_ids("2,3", {1: (10, 20), 2: (40, 50)}),
            ([], "disconnected"),
        )

    def test_sampling_preserves_endpoints(self):
        sampled = sample_points([[float(i), float(i)] for i in range(101)], 32)
        self.assertEqual(tuple(sampled[0]), (0.0, 0.0))
        self.assertEqual(tuple(sampled[-1]), (100.0, 100.0))
        self.assertLessEqual(len(sampled), 32)


if __name__ == "__main__":
    unittest.main()
