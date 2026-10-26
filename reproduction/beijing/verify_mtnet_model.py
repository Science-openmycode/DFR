"""Isolated author-model CUDA forward/backward with file-based miniature inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();root=a.root.resolve();out=a.out.resolve()
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True);started=time.perf_counter();result={'passed':False}
    try:
        lock=json.loads((root/'canonical_mtnet_source_lock.json').read_text())
        for name,digest in lock['files_sha256'].items():
            assert hashlib.sha256((root/'official'/name).read_bytes()).hexdigest()==digest.lower(),name
        fixture=out/'fixture';fixture.mkdir()
        (fixture/'edge_property.txt').write_text('1,100,1,0,fixture\n2,100,1,90,fixture\n',encoding='utf-8')
        (fixture/'edge_adj.txt').write_text('2\n1\n',encoding='utf-8')
        shutil.copy2(root/'official/data/demo/temporal_32.emb',fixture/'temporal_32.emb')
        import torch
        if not torch.cuda.is_available():raise RuntimeError('CUDA required; no CPU fallback')
        sys.path.insert(0,str(root/'official'))
        from util import config
        config.DATA_BASE=str(out)+'/'
        config.CITY='fixture'
        import mtnet
        torch.manual_seed(42)
        model=mtnet.Model()
        x=torch.tensor([[1,2]],device='cuda',dtype=torch.long)
        departure=torch.zeros_like(x)
        px,pt=model(x,departure)
        if not torch.isfinite(px).all() or not torch.isfinite(pt).all():
            raise RuntimeError('Nonfinite forward output')
        loss=px.mean()+pt.mean();loss.backward()
        grads=[p.grad for p in model.parameters() if p.grad is not None]
        if not grads or not all(torch.isfinite(g).all() for g in grads):
            raise RuntimeError('Missing or nonfinite gradients')
        result.update(passed=True,device=str(next(model.parameters()).device),
                      output_shapes=[list(px.shape),list(pt.shape)],gradient_tensors=len(grads),
                      peak_cuda_bytes=torch.cuda.max_memory_allocated())
    except Exception as exc:result.update(error=f'{type(exc).__name__}: {exc}')
    result.update(seconds=time.perf_counter()-started,
                  scope='Author model and file loaders, CUDA forward/backward only; no optimizer update, DP training, or formal release')
    (out/'report.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result));return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
