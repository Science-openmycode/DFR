import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.separate import validate_matcher_binding
from algorithms.measurements.frozen_adapter import verify_sources
from tools import write_batch_commands as planner

class DeliveryRepair(unittest.TestCase):
    def test_restored_source_inventory(self):
        self.assertEqual(len(verify_sources()),64)

    def test_exact_matchers(self):
        c=json.loads((ROOT/'configs/beijing.json').read_text())
        for router in ('FMM','STMatch'):validate_matcher_binding(c,ROOT,router)

    def test_public_runtime_import(self):
        p=ROOT/'legacy/evaluation/generation/common/runtime.py'
        s=importlib.util.spec_from_file_location('restored_runtime',p)
        m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
        self.assertEqual(m.PUBLIC_RELEASE,ROOT/'legacy/evaluation')
        self.assertEqual(m.dataset_config('geolife')['bbox'],[39.75,40.15,116.1,116.65])

    def test_new_plan_changes_io_not_algorithm_options(self):
        with tempfile.TemporaryDirectory(prefix='DFR plan with spaces ') as td:
            root=Path(td);doc=root/'commands.md'
            doc.write_text('```powershell\npython synthesize.py --config old.json --epsilon 0.4 --seed 9 --out results/old/full\npython prep.py --time-binding resources/mtnet/time_binding.json --raw-reference resources/mtnet/original_timestamp_reference.pkl\n```\n',encoding='utf-8')
            (root/'old.json').write_text(json.dumps({'epsilon':.4,'seed':9,'k':48,'paths':{},'batch':'old'}))
            cfg=root/'new.json';cfg.write_text(json.dumps({'dataset':'beijing','frozen_dataset_id':'new',
                'batch':'new_batch','slots':2,'paths':{'prepared':'prepared','network':'network.shp'}}))
            with patch.object(planner,'ROOT',root),patch.object(planner,'DOCS',['commands.md']),patch('preprocess.dataset_contract.validate_dataset',return_value={'dataset_id':'new'}):
                planner.generate(cfg,root/'plan',root/'my times.json',root/'raw coords.pkl')
            c=json.loads((root/'plan/configs/old.json').read_text())
            self.assertEqual((c['epsilon'],c['seed'],c['k']),(.4,9,48))
            self.assertEqual(c['frozen_dataset_id'],'new')
            text=(root/'plan/commands/commands.md').read_text()
            self.assertIn('--out results/new_batch/old/full',text)
            self.assertIn('--config plan/configs/old.json',text)
            self.assertIn('--time-binding "',text)
            self.assertNotIn('resources/mtnet/',text)
            self.assertEqual(json.loads((root/'plan/manifest.json').read_text())['status'],'PLAN_ONLY_NOT_EXECUTED')

if __name__=='__main__':unittest.main()
