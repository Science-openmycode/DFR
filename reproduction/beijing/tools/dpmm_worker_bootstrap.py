"""Importable Windows-spawn boundary for the validated, unchanged DPMM call."""
import hashlib
import importlib.util
import os
from pathlib import Path
import sys

_reference = None


def load_file(name, filename, expected):
    filename = Path(filename)
    with filename.open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest() != expected:
            raise ValueError('DPMM worker source changed: '+str(filename))
    spec=importlib.util.spec_from_file_location(name,filename)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module


def initialize(config):
    global _reference
    _reference = load_file('dfr_dpmm_worker_reference',os.environ['DFR_DPMM_ADAPTER'],
                           os.environ['DFR_DPMM_ADAPTER_SHA256'])
    optimizer = load_file('dfr_dpmm_worker_optimizer',os.environ['DFR_DPMM_OPTIMIZER'],
                          os.environ['DFR_DPMM_OPTIMIZER_SHA256'])
    _reference.install_semantic_path_cache=optimizer.install_semantic_path_cache
    _reference._init_worker(config)
    print('DPMM_ACCELERATED_WORKER_READY',os.getpid(),flush=True)


def process(item):
    if _reference is None:
        raise RuntimeError('DPMM worker was not initialized')
    return _reference._worker_process(item)
