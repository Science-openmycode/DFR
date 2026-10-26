"""Make saved coordinate ancestry local; preserve original sidecars and payload bytes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
REMOTE=None


def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def relocate(path,depth=0):
    if depth>32:raise ValueError('Ancestor cycle')
    sidecar=path.with_name(path.name+'.manifest.json')
    if not sidecar.exists():return 0
    record=json.loads(sidecar.read_text(encoding='utf-8-sig'))
    source=record.get('route_source') or record.get('inputs',{}).get('source')
    if not isinstance(source,dict) or not source.get('path'):return 0
    old=Path(source['path'])
    if not old.is_absolute():old=sidecar.parent/old
    if old.resolve().is_relative_to(ROOT):return 0
    if not old.exists():
        cfg=json.loads((ROOT/'configs/portable_supplement.json').read_text(encoding='utf-8'))
        local=[ROOT/r['coordinates'] for r in cfg['tstr_releases'].values()]
        found=next((p for p in local if sha(p)==source['sha256']),None)
        if found is not None:old=found
        elif REMOTE and old.as_posix().startswith('D:/MTR/'):
            downloaded=ROOT/'supplement/transferred_ancestors'/source['sha256']/old.name
            downloaded.parent.mkdir(parents=True,exist_ok=True)
            subprocess.run(['scp','-q',REMOTE+':'+old.as_posix(),str(downloaded)],check=True)
            old=downloaded
        else:raise FileNotFoundError('Cannot package referenced ancestor '+str(old))
    if sha(old)!=source['sha256']:raise ValueError('Ancestor changed')
    dest=path.parent/'ancestors'/source['sha256']/old.name
    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(old,dest)
    old_sidecar=old.with_name(old.name+'.manifest.json')
    if old_sidecar.exists():shutil.copy2(old_sidecar,dest.with_name(dest.name+'.manifest.json'))
    count=relocate(dest,depth+1)
    original=sha(sidecar)
    archive=ROOT/'supplement/original_sidecars'/f'{original}.json'
    archive.parent.mkdir(parents=True,exist_ok=True)
    if not archive.exists():shutil.copy2(sidecar,archive)
    source['path']=str(dest.relative_to(path.parent)).replace('\\','/')
    record['relocation']={'original_manifest_sha256':original,'payload_unchanged':True,'ancestry_payload_sha256':source['sha256']}
    sidecar.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return count+1


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--remote-host')
    REMOTE=parser.parse_args().remote_host
    cfg=json.loads((ROOT/'configs/portable_supplement.json').read_text(encoding='utf-8'))
    print({'relocated':sum(relocate(ROOT/r['coordinates']) for r in cfg['tstr_releases'].values())})
