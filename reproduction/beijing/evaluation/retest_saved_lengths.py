"""Re-evaluate ONLY length fidelity on existing full-population coordinate views."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import pickle
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from evaluation.audit_metric_fixes import PROTOCOL, length_statistics, preserve_slots


def sha(file):
    with Path(file).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--real',type=Path,required=True)
    p.add_argument('--synthetic',type=Path,required=True)
    p.add_argument('--old-score',type=Path,required=True)
    p.add_argument('--legacy',type=Path,required=True)
    p.add_argument('--expected-slots',type=int,required=True)
    p.add_argument('--real-sha256',required=True,help='Frozen reference hash, not a name-only binding')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    legacy=a.legacy.resolve()/'evaluation'
    sys.path[:0]=[str(legacy),str(legacy/'pipeline')]
    import evaluate_kdd_revised_statistics as stats
    from evaluation import audit_metric_fixes
    inputs={str(f.resolve()):sha(f) for f in (a.real,a.synthetic,a.old_score,Path(__file__),
                                             Path(stats.__file__),Path(audit_metric_fixes.__file__))}
    started=time.perf_counter()
    old=json.loads(a.old_score.read_text(encoding='utf-8'))
    if sha(a.real)!=a.real_sha256 or Path(old['protocol']['real_spec']).resolve()!=a.real.resolve():
        raise ValueError('Real reference differs from frozen input or saved score reference')
    # The existing evaluation ledger must bind this exact synthetic file.
    ledger=json.loads(a.old_score.with_name('manifest.json').read_text(encoding='utf-8'))
    if ledger['inputs']['synthetic']['sha256']!=sha(a.synthetic):
        raise ValueError('Old score does not bind the supplied synthetic input')
    if ledger['outputs']['metrics.json']!=sha(a.old_score):
        raise ValueError('Old score hash changed')
    with a.real.open('rb') as f:real=preserve_slots(pickle.load(f))
    with a.synthetic.open('rb') as f:syn=preserve_slots(pickle.load(f))
    if len(real)!=a.expected_slots or len(syn)!=a.expected_slots:
        raise ValueError('Do not change either population denominator')
    result=length_statistics(real,syn,stats)
    result.update(protocol=PROTOCOL,scope='Full-population length-only replay; not all45 metrics',
                  old_path_length_jsd=old['metrics']['path_length_jsd'],
                  real_slots=len(real),synthetic_slots=len(syn),inputs_sha256=inputs,
                  seconds=time.perf_counter()-started,command=[sys.executable,*sys.argv])
    if any(sha(f)!=h for f,h in inputs.items()):raise RuntimeError('Input changed during retest')
    a.out.mkdir(parents=True)
    (a.out/'length_retest.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('old_path_length_jsd','path_length_jsd','real_counted',
        'synthetic_counted','synthetic_overflow','seconds')}))


if __name__=='__main__':main()
