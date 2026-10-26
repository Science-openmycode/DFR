"""Import exact research resources from an authorized local delivery folder."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

ROOT=Path(__file__).resolve().parent
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def bound(root,relative):
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Path escapes resource root')
    return path
def valid(path,item):
    return path.is_file() and path.stat().st_size==item['bytes'] and sha(path)==item['sha256']
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,help='Authorized complete beijing_delivery_20261018 directory; copied unchanged, not uploaded')
    p.add_argument('--check-only',action='store_true',help='Verify assets already imported; no copying')
    a=p.parse_args()
    if not a.check_only and a.source is None:p.error('--source required unless --check-only')
    manifest=json.loads((ROOT/'external_assets.json').read_text(encoding='utf-8'))
    missing=[];copied=0
    for index,item in enumerate(manifest['files'],1):
        target=bound(ROOT,item['path'])
        if target.exists():
            if not valid(target,item):raise ValueError('Existing resource differs; not overwritten: '+item['path'])
        elif a.check_only:missing.append(item['path'])
        else:
            source=bound(a.source.resolve(),item['path'])
            if not valid(source,item):raise ValueError('Wrong or missing source resource: '+item['path'])
            target.parent.mkdir(parents=True,exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='.asset-',dir=target.parent) as temp:
                staged=Path(temp)/'payload';shutil.copy2(source,staged)
                if not valid(staged,item):raise ValueError('Copy changed: '+item['path'])
                if target.exists():raise FileExistsError(target)
                staged.replace(target)
            copied+=1
        if index%100==0:print(f'CHECKED {index}/{len(manifest["files"])}',flush=True)
    report={'status':'MISSING' if missing else 'VERIFIED','files':len(manifest['files']),'copied':copied,'missing':missing}
    print(json.dumps(report,ensure_ascii=False))
    if missing:raise SystemExit(2)
if __name__=='__main__':main()
