"""Verify a finished train-only DPMM run and stage unchanged evaluation slots.

Research provenance only, not a privacy proof. Never generates, routes or scores.
Partial output, missing outer execution evidence and full-corpus releases fail.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from preprocess.dataset_contract import sha
from tools.check_documented_command import check
from tools.stage_dpmm_evaluation_slots import stage
from tools.audit_readme_commands import split_windows


def is_train_generation(command):
    """Check argv, not a machine-specific interpreter spelling."""
    argv=split_windows(command)
    if len(argv)<4 or Path(argv[0]).name.lower() not in ('python','python.exe'):
        return False
    if Path(argv[1]).as_posix()!='synthesize_dpmm.py':
        return False
    return argv.count('--split')==1 and argv.index('--split')+1<len(argv) and argv[argv.index('--split')+1]=='train'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def prepare(directory, config, ledger, document, validation, out):
    directory, out = Path(directory), Path(out)
    if out.exists():
        raise FileExistsError(out)
    c = read(config)
    paths = {k: (ROOT / v).resolve() for k, v in c['paths'].items()}
    split = read(paths['split_audit'])
    train_sha, test_sha = sha(paths['train']), sha(paths['test'])
    if (split.get('schema') != 'verified_disjoint_split_v1'
            or split.get('status') != 'passed'
            or split.get('all_source_indices_used_once') is not True
            or split.get('train_sha256') != train_sha
            or split.get('test_sha256') != test_sha or train_sha == test_sha
            or split.get('train_count') != c['train_slots']
            or split.get('test_count') != c['test_slots']):
        raise ValueError('Wrong or unverified train/test split')
    execution = read(directory / 'new_dataset_execution.json')
    v = read(validation)
    if (execution.get('status') != 'DONE' or execution.get('population') != 'train'
            or execution.get('input_count') != c['train_slots']
            or execution.get('dataset_id') != c['frozen_dataset_id']
            or execution.get('input_sha256') != train_sha
            or execution.get('rematched') is not False
            or execution.get('validation_sha256') != sha(validation)
            or not v.get('complete') or not v.get('passed')
            or v.get('protocol') != 'accelerated-only-process-validation-v1'
            or v.get('tested_records') != 60 or v.get('target_records') != 60
            or len(v.get('sixty_record_validation', {}).get('results', [])) != 60
            or len({r['index'] for r in v['sixty_record_validation']['results']}) != 60
            or v.get('slow_reference_executed') is not False
            or v.get('population') != 'train' or v.get('input_sha256') != train_sha
            or v.get('input_count') != c['train_slots']
            or v.get('dataset_id') != c['frozen_dataset_id']
            or v.get('public_osm_sha256') != execution.get('osm_sha256')
            or v.get('recommended_workers') != execution.get('workers')
            or not execution.get('adapter_sha256') or not execution.get('optimizer_sha256')
            or v.get('adapter_sha256') != execution.get('adapter_sha256')
            or v.get('optimization_sha256') != execution.get('optimizer_sha256')
            or v.get('public_parameters', {}).get('epsilon') != c['epsilon']):
        raise ValueError('Incomplete or mismatched train-only DPMM execution')
    for name in ('dpmm.pkl', 'dpmm.json'):
        if execution.get('outputs', {}).get(name) != sha(directory / name):
            raise ValueError('Native output hash mismatch: ' + name)
    rows = [json.loads(line) for line in Path(ledger).read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    verified = [r for r in rows if r.get('phase') == 'verified'
                and r.get('execution_sha256') == sha(directory / 'new_dataset_execution.json')]
    if len(verified) != 1:
        raise ValueError('Require one verified actual outer execution receipt')
    receipt = verified[0]
    command = receipt['actual_outer_command']
    check(document, receipt['line'], command, receipt['document_sha256'])
    if (receipt.get('exit_code') != 0 or not receipt.get('seconds', 0) > 0
            or not is_train_generation(command)
            or receipt.get('outputs_sha256') != execution['outputs']
            or not any(r.get('phase') == 'start' and r.get('actual_outer_command') == command
                       and r.get('output') == receipt.get('output') for r in rows)
            or not any(r.get('phase') == 'finish' and r.get('actual_outer_command') == command
                       and r.get('exit_code') == 0 for r in rows)):
        raise ValueError('Outer command did not finish and verify as documented')
    meta = read(directory / 'dpmm.json')
    if meta.get('input_count') != c['train_slots']:
        raise ValueError('Native manifest belongs to another population')
    staged = stage(release=directory / 'dpmm.pkl', manifest=directory / 'dpmm.json', out_dir=out)
    if (staged['inputs']['release']['sha256'] != execution['outputs']['dpmm.pkl']
            or staged['inputs']['manifest']['sha256'] != execution['outputs']['dpmm.json']):
        raise ValueError('Native source changed before staging')
    record = dict(schema='executed_train_only_generation_v1', status='passed',
        generator='DPMM preserved native generator with validated path-cache acceleration',
        input_policy='train_only_explicit_generator_input', returncode=0,
        train_sha256=train_sha, test_sha256=test_sha, dataset_id=c['frozen_dataset_id'],
        source_sha256=execution['adapter_sha256'], optimizer_sha256=execution['optimizer_sha256'],
        command=command, public_slot_count=c['train_slots'], epsilon=c['epsilon'],
        privacy_scope=execution['privacy_scope'],
        evidence_scope=receipt.get('evidence_scope','Observed completed outer CLI and hash-bound train input; not a formal noninterference or DP proof'),
        execution_sha256=sha(directory / 'new_dataset_execution.json'),
        outer_ledger_sha256=sha(ledger), document_sha256=sha(document),
        validation_sha256=sha(validation), split_audit_sha256=sha(paths['split_audit']),
        native_outputs=execution['outputs'],
        outputs={'coordinates.pkl': staged['output']['sha256']})
    (out / 'lineage.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    return record


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('directory', 'config', 'ledger', 'document', 'validation', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    print(json.dumps(prepare(**vars(p.parse_args())), indent=2))
