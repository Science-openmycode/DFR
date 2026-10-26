"""Package the complete private candidate, excluding runs, caches and environments."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DIRECTORIES=('algorithms','configs','deployment','evaluation','experiments','legacy',
             'plotting','preprocess','resources','tests','tools','vendor')
EXCLUDE={'__pycache__','.pytest_cache','.git','.venv'}

def collect_files(root):
    root=Path(root)
    files=[f for f in root.iterdir() if f.is_file() and
           (f.suffix in ('.py','.md','.txt') or f.name in ('manifest.json','pytest.ini'))
           and f.name!='environment_freeze.txt']
    for directory in DIRECTORIES:
        for f in (root/directory).rglob('*'):
            if f.is_file() and not (set(f.relative_to(root).parts)&EXCLUDE) and f.suffix not in ('.pyc','.pyo'):
                files.append(f)
    return sorted(files)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();out=a.out.resolve()
    if out.exists():raise FileExistsError(out)
    files=collect_files(ROOT)
    bindings={};total=0
    for f in sorted(files):
        with f.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        bindings[f.relative_to(ROOT).as_posix()]={'sha256':digest,'bytes':f.stat().st_size}
        total+=f.stat().st_size
    manifest={'scope':'PRIVATE candidate, not public release; no formal result reuse',
              'files':bindings,'total_bytes':total,'file_count':len(bindings)}
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for rel in bindings:z.write(ROOT/rel,rel)
        z.writestr('delivery_package_manifest.json',json.dumps(manifest,indent=2))
    with out.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    print(json.dumps({'archive':str(out),'sha256':digest,'bytes':out.stat().st_size,
                      'files':len(bindings),'uncompressed_bytes':total}))

if __name__=='__main__':main()
