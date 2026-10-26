import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

SCRIPT=Path(__file__).resolve().parents[1]/'preprocess/fetch_geolife.py'
spec=importlib.util.spec_from_file_location('fetch',SCRIPT)
fetch=importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)

class SafeExtraction(unittest.TestCase):
    def test_valid_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=root/'test.zip'; out=root/'out'
            with zipfile.ZipFile(archive,'w') as z:z.writestr('Data/000/a.plt','example')
            fetch.extract(archive,out)
            self.assertEqual((out/'Data/000/a.plt').read_text(),'example')
            with self.assertRaises(ValueError):fetch.extract(archive,out)

    def test_unsafe_paths(self):
        for name in ['../escape','C:/escape','..\\escape']:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); archive=root/'test.zip'
                with zipfile.ZipFile(archive,'w') as z:z.writestr(name,'bad')
                with self.assertRaises(ValueError):fetch.extract(archive,root/'out')
                self.assertFalse((root/'out').exists())

if __name__=='__main__':unittest.main()
