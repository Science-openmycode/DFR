"""Record a documented direct command before/after the caller runs it.

This recorder does not launch the generator. The caller supplies its actual
exit code immediately after the literal command; this is not OS attestation.
"""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from preprocess.dataset_contract import sha
from tools.check_documented_command import check


def record(phase,document,output,ledger,exit_code=None):
    document=Path(document);output=Path(output);ledger=Path(ledger)
    if phase=='start':
        if ledger.exists() or output.exists():raise FileExistsError('Use a new output and ledger')
        candidates=[(n,line) for n,line in enumerate(document.read_text(encoding='utf-8-sig').splitlines(),1)
                    if line.startswith('.venv/Scripts/python.exe synthesize_dpmm.py ') and '--out '+output.as_posix() in line]
        if len(candidates)!=1:raise ValueError('Require one literal generator command')
        number,command=candidates[0];digest=sha(document)
        check(document,number,command,digest)
        item=dict(phase='start',actual_outer_command=command,line=number,document_sha256=digest,
                  output=str(output),started=time.time(),evidence_scope='Caller records direct documented command and its shell exit code; no automatic process attestation')
        ledger.parent.mkdir(parents=True,exist_ok=True)
        ledger.write_text(json.dumps(item)+'\n',encoding='utf-8')
        print(command);return
    rows=[json.loads(s) for s in ledger.read_text(encoding='utf-8').splitlines()]
    if len(rows)!=1 or rows[0]['phase']!='start':raise ValueError('Already finished or invalid start')
    start=rows[0]
    check(document,start['line'],start['actual_outer_command'],start['document_sha256'])
    if str(output)!=start['output'] or exit_code is None:raise ValueError('Missing actual shell exit or mismatched output')
    finish=dict(start,phase='finish',exit_code=exit_code,seconds=time.time()-start['started'])
    with ledger.open('a',encoding='utf-8') as f:f.write(json.dumps(finish)+'\n')
    if exit_code!=0:raise RuntimeError('Generator failed; failure preserved, no verified entry')
    execution=output/'new_dataset_execution.json';meta=json.loads(execution.read_text(encoding='utf-8'))
    if meta['status']!='DONE':raise ValueError('Incomplete generation')
    for name,digest in meta['outputs'].items():
        if sha(output/name)!=digest:raise ValueError('Changed generation output')
    verified=dict(finish,phase='verified',execution_sha256=sha(execution),outputs_sha256=meta['outputs'])
    with ledger.open('a',encoding='utf-8') as f:f.write(json.dumps(verified)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('phase',choices=['start','finish'])
    for key in ['document','output','ledger']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--exit-code',type=int)
    record(**vars(p.parse_args()))
