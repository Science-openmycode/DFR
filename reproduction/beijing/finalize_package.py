"""Normalize package metadata and record the actually imported dependency versions."""
import json
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parent
for name in ('beijing.json','beijing_tstr.json'):
    f=ROOT/'configs'/name;c=json.loads(f.read_text(encoding='utf-8'))
    c.pop('ubodt_manifest',None)
    b=c.get('matcher_compatibility',{})
    for k in ('original_source','source','input_config'):b.pop(k,None)
    f.write_text(json.dumps(c,ensure_ascii=True,indent=2),encoding='utf-8')
shutil.copyfile(ROOT/'configs/beijing.json',ROOT/'configs/beijing.yaml')
r=json.loads((ROOT/'validation/preflight_01.json').read_text())
(ROOT/'requirements-validated.txt').write_text('\n'.join(k+'=='+v for k,v in sorted(r['versions'].items()))+'\n',encoding='utf-8')
