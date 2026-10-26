"""Run only road preprocessing and selection review, never synthesis or scoring."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,default=ROOT/'configs/preprocess_beijing_8_16.json')
    p.add_argument('--out',type=Path,required=True,help='New audit/prepared directory; never overwrite')
    p.add_argument('--dry-run',action='store_true',help='Show all resolved arguments without running')
    p.add_argument('--accept-reviewed-subset',help='SHA256 of the explicitly approved review report')
    a=p.parse_args();cfg=json.loads(a.config.read_text(encoding='utf-8'))
    command=[sys.executable,'-X','utf8',str(ROOT/'preprocess/road_dataset.py')]
    for key,value in cfg['paths'].items():command.extend(['--'+key,str((ROOT/value).resolve())])
    for key,value in cfg['parameters'].items():command.extend(['--'+key,*map(str,value if isinstance(value,list) else [value])])
    command.extend(['--out',str(a.out.resolve())])
    if a.accept_reviewed_subset:command.extend(['--accept-reviewed-subset',a.accept_reviewed_subset])
    if a.dry_run:print(json.dumps(command,ensure_ascii=False,indent=2));return
    raise SystemExit(subprocess.run(command,cwd=ROOT).returncode)

if __name__=='__main__':main()
