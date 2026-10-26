"""Deployment checks only; no trajectories or experiments are generated."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('asset_import',ROOT/'import_external_assets.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class AssetImportTests(unittest.TestCase):
    def test_copy_verify_reuse_and_refuse_changed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'target';root.mkdir();source=Path(temp)/'source';source.mkdir()
            (source/'a.bin').write_bytes(b'fixture')
            (root/'external_assets.json').write_text(json.dumps({'files':[{'path':'a.bin','bytes':7,'sha256':module.sha(source/'a.bin')}]}))
            with patch.object(module,'ROOT',root),contextlib.redirect_stdout(io.StringIO()):
                with patch.object(sys,'argv',['import','--source',str(source)]):module.main()
                self.assertEqual((root/'a.bin').read_bytes(),b'fixture')
                with patch.object(sys,'argv',['import','--check-only']):module.main()
                (root/'a.bin').write_bytes(b'changed')
                with patch.object(sys,'argv',['import','--source',str(source)]),self.assertRaises(ValueError):module.main()
                self.assertEqual((root/'a.bin').read_bytes(),b'changed')
    def test_reject_escape(self):
        with tempfile.TemporaryDirectory() as temp,self.assertRaises(ValueError):module.bound(Path(temp),'../outside')

if __name__=='__main__':unittest.main()
