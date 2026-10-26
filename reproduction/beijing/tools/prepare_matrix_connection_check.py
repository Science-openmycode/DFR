"""Stage two unchanged saved score pairs for a new-collector CLI wiring check."""
import csv
import json
from pathlib import Path
import shutil
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.collect_frozen_matrix import sha


if __name__=='__main__':
    target=ROOT/'validation/connection_cli'
    if target.exists():raise FileExistsError(target)
    with (ROOT/'reference_results/matrix/matrix_sources.csv').open(encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    evidence=[]
    for row,label in [('SPRT + STMatch','stat'),('MTR-DFR','native')]:
        selected=[r for r in rows if r['row']==row and r['column']=='BTF']
        if len(selected)!=1:raise ValueError(row)
        r=selected[0]
        method,router=('MTR-DFR','Origin') if row=='MTR-DFR' else ('SPRT','STMatch')
        folder=target/label/'scores'/method/router;folder.mkdir(parents=True)
        for key,name in [('result','metrics.json'),('manifest','manifest.json')]:
            source=ROOT/r[key]
            if sha(source)!=r[key+'_sha256']:raise ValueError('Changed saved source')
            shutil.copy2(source,folder/name)
        evidence.append({'row':row,'value':float(r['value']),'source_sha256':r['result_sha256']})
    (target/'expected.json').write_text(json.dumps({'scope':'Interface check with two existing score files, not new algorithm runs','cells':evidence},indent=2),encoding='utf-8')
    print('STAGED_TWO_EXISTING_SCORE_PAIRS_NO_REEVALUATION')
