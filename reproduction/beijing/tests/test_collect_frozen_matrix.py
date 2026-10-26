import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('collector', Path(__file__).parents[1]/'tools/collect_frozen_matrix.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MatrixTests(unittest.TestCase):
    def test_native_one_row(self):
        self.assertEqual(m.row_label('DPMM','Origin'),'DPMM')
        self.assertEqual(m.row_label('SPRT','MM2-MDP'),'SPRT + MM2-MDP')

    def test_zero_na_missing_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cell = root/'scores/SPRT/Nearest'
            cell.mkdir(parents=True)
            result = cell/'metrics.json'
            result.write_text(json.dumps({'RoadYield':0,'BTF':None,
                                         'metric_status':{'BTF':'NA'}}))
            meta = dict(inputs={'real_routes':{'sha256':'0a0b11c0fef09bf3267ffdeca9d9202bedb8bfd609cb7da5c381ed08dca4907c'}},
                        real={'reference_slots':15730},synthetic={'slots':15730},
                        outputs={'metrics_json':{'sha256':m.sha(result)}})
            (cell/'manifest.json').write_text(json.dumps(meta))
            rows = m.collect(root,dict(rows=['SPRT + Nearest'],columns=['RoadYield','BTF','Grid']))
            self.assertEqual([r['status'] for r in rows],['ZERO','NA','MISSING'])
            result.write_text('{}')
            with self.assertRaises(ValueError):
                m.collect(root,dict(rows=['SPRT + Nearest'],columns=['RoadYield']))


if __name__ == '__main__':
    unittest.main()
