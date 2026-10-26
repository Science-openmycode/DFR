import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('independent', Path(__file__).parents[1] / 'tools/independent_road_arithmetic.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ArithmeticTests(unittest.TestCase):
    def setUp(self):
        self.cache = dict(edge_nodes={1:(0,1),2:(1,2),3:(1,3)}, outdegree={0:1,1:2},
                          labels96={0:0,1:1,2:2,3:3}, labels24={0:0,1:1,2:2,3:3})
        self.raw = [dict(accepted=True,cpath=[1,2]),dict(accepted=True,cpath=[1,3])]

    def test_identity(self):
        a = m.accumulate(self.raw, self.cache)
        values = m.statistics(a, a)
        self.assertEqual(len(values), 17)
        for value in values.values():
            self.assertAlmostEqual(value, 1)

    def test_empty_slots_preserved(self):
        a = m.accumulate(self.raw, self.cache)
        b = m.accumulate(self.raw + [dict(accepted=False,cpath=[])]*2, self.cache)
        values = m.statistics(a, b)
        self.assertEqual(values['RoadYield'], .5)
        self.assertEqual(values['BTF'], .5)
        self.assertEqual(values['FamilyCPC'], .5)
        for name in ('RC-CPC','EdgeCPC','TurnCPC'):
            self.assertEqual(values[name], 1)

    def test_disconnected_rejected(self):
        a = m.accumulate([dict(accepted=True,cpath=[2,3])],self.cache)
        self.assertEqual(a['slots'], 1)
        self.assertEqual(a['valid'], 0)

    def test_wrong_representation_refused(self):
        with self.assertRaises(ValueError):
            m.accumulate([[1,2]],self.cache)


if __name__ == '__main__':
    unittest.main()
