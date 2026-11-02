"""Install the tested FMM safety build; preserve config and binary backups."""
import argparse,hashlib,json,shutil,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--include-stmatch',action='store_true',help='Also install the tested STMatch statistics build')
    a=p.parse_args(); config=a.config.resolve()
    c=json.loads(config.read_text(encoding='utf-8-sig'))
    source=ROOT.parents[1]/'public_assets/matcher/fmm.exe'
    binding=json.loads((ROOT/'resources/fmm/safety_build.json').read_text(encoding='utf-8'))
    if sha(source)!=binding['fmm_sha256']:raise ValueError('Safety binary differs from tested build')
    target=(ROOT/c['paths']['fmm']).resolve()
    if not target.is_relative_to(ROOT):raise ValueError('Configured binary is outside this checkout')
    st_source=ROOT.parents[1]/'public_assets/matcher/stmatch.exe'
    st_target=None
    if a.include_stmatch:
        if sha(st_source)!=binding['stmatch_sha256']:raise ValueError('STMatch binary differs from tested build')
        st_target=(ROOT/c['paths']['stmatch']).resolve()
        if not st_target.is_relative_to(ROOT):raise ValueError('Configured STMatch is outside this checkout')
    import psutil
    for proc in psutil.process_iter(['cmdline']):
        try:
            argv=proc.info['cmdline'] or []
            if any(Path(word).name.lower()=='route.py' for word in argv) and Path(proc.cwd()).resolve()==ROOT:
                raise RuntimeError('Routing is active here; install after it exits')
        except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    backup=ROOT/'results/fmm_safety_installations'/time.strftime('%Y%m%d_%H%M%S')
    backup.mkdir(parents=True,exist_ok=False)
    shutil.copy2(config,backup/'config.before.json')
    before=sha(target) if target.exists() else None
    if target.exists():shutil.copy2(target,backup/'fmm.before.exe')
    if target!=source:
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)
    if 'matcher_compatibility' in c:c['matcher_compatibility']['fmm_sha256']=sha(target)
    if st_target is not None:
        if st_target.exists():shutil.copy2(st_target,backup/'stmatch.before.exe')
        st_target.parent.mkdir(parents=True,exist_ok=True)
        if st_target!=st_source:shutil.copy2(st_source,st_target)
        if 'matcher_compatibility' in c:c['matcher_compatibility']['stmatch_sha256']=sha(st_target)
    c['fmm_safety_build']=dict(binding,installed_binary=str(target),previous_sha256=before,
                               backup=str(backup),parameters_changed=False)
    config.write_text(json.dumps(c,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    receipt=dict(config=str(config),binary=str(target),binary_sha256=sha(target),
                 config_sha256=sha(config),backup=str(backup),parameters_changed=False)
    (backup/'installation.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False))
if __name__=='__main__':main()
