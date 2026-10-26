"""Verify locked MTNet code and a tiny CUDA computation, without training."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    started=time.perf_counter();errors=[];info={}
    root=args.root.resolve()
    try:
        lock=json.loads((root/'canonical_mtnet_source_lock.json').read_text(encoding='utf-8'))
        for name,expected in lock['files_sha256'].items():
            with (root/'official'/name).open('rb') as stream:
                if hashlib.file_digest(stream,'sha256').hexdigest()!=expected.lower():
                    raise ValueError('MTNet locked source changed: '+name)
        import torch
        info.update(torch=torch.__version__,cuda=torch.version.cuda)
        if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable; no silent CPU fallback')
        value=torch.ones(8,device='cuda').sum().item()
        if value!=8:raise RuntimeError('CUDA tensor result mismatch')
        info.update(device=torch.cuda.get_device_name(0),tensor_sum=value)
        spec=importlib.util.spec_from_file_location('portable_mtnet_trainer',root/'train_native_mtnet_dpsgd_paper.py')
        trainer=importlib.util.module_from_spec(spec);sys.modules[spec.name]=trainer
        spec.loader.exec_module(trainer)
    except Exception as exc:errors.append(f'{type(exc).__name__}: {exc}')
    info.update(passed=not errors,errors=errors,seconds=time.perf_counter()-started,
                scope='source hashes, trainer import and tiny CUDA tensor only; no model training or release')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(info,indent=2),encoding='utf-8')
    print(json.dumps(info));return 0 if info['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
