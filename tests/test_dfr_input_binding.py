import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT/"generation/mtr_dfr/run.py"

class DFRInputBindingTest(unittest.TestCase):
    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            result = subprocess.run([sys.executable,str(SCRIPT),"--seed","1",
                "--real-matched",str(folder/"real.pkl.gz"),"--edge-cache",str(folder/"cache.pkl.gz"),
                "--network",str(folder/"network.shp"),"--out-dir",str(folder)],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b"Output directory already exists",result.stderr)

    def test_mismatched_public_network_is_rejected_before_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            for name in ("real.pkl.gz","cache.pkl.gz","network.shp"):
                (folder/name).write_bytes(b"fixture")
            (folder/"cache.manifest.json").write_text(json.dumps({"network_sha256":"0"*64}),encoding="utf-8")
            result = subprocess.run([sys.executable,str(SCRIPT),"--seed","1",
                "--real-matched",str(folder/"real.pkl.gz"),"--edge-cache",str(folder/"cache.pkl.gz"),
                "--network",str(folder/"network.shp"),"--out-dir",str(folder/"out")],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn(b"network binding mismatch",result.stderr)
            self.assertFalse((folder/"out").exists())

if __name__ == "__main__":
    unittest.main()
