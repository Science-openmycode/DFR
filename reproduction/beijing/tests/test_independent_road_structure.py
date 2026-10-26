import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
import independent_road_structure as m


class StructureTests(unittest.TestCase):
    def setUp(self):
        self.cache = dict(edge_nodes={1:(0,1),2:(1,2),3:(2,1),4:(1,3)},
                          labels24={i:i for i in range(4)},labels96={i:i for i in range(4)},
                          labels384={i:i for i in range(4)})
        self.lengths = {(0,1):1,(1,2):2,(2,1):3,(1,3):4}
        self.raw = [dict(accepted=True,cpath=[1,2,3,2,3,4])]

    def test_closed_walk_totals(self):
        a = m.accumulate(self.raw,self.cache,self.lengths)
        self.assertEqual(a['totals']['TotalLengthRetention'],15)
        self.assertEqual(a['totals']['BackboneLengthRetention'],5)
        self.assertEqual(a['totals']['ClosedLengthRetention'],10)
        self.assertEqual(a['totals']['ClosedSegmentRetention'],2)
        self.assertEqual(a['totals']['RepeatedEdgeRetention'],2)

    def test_identity_and_empty_slot(self):
        a = m.accumulate(self.raw,self.cache,self.lengths)
        b = m.accumulate(self.raw+[dict(accepted=False,cpath=[])],self.cache,self.lengths)
        self.assertEqual(len(m.statistics(a,a)),7)
        for value in m.statistics(a,a).values():
            self.assertAlmostEqual(value,1)
        for value in m.statistics(a,b).values():
            self.assertAlmostEqual(value,.5)


if __name__ == '__main__':
    unittest.main()
