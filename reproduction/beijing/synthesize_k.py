"""Relocated entry to the preserved K experiment adapter, with package-local paths."""
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parent

if __name__=='__main__':
    path=ROOT/'supplement/k_original/synthesize_dfr.py'
    spec=importlib.util.spec_from_file_location('preserved_k_entry',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.ROOT=ROOT
    module.main()
