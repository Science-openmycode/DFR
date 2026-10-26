"""Verify completed train-only MTNet artifacts and record observed CLI provenance."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from preprocess.dataset_contract import sha
from register_mtnet import validate_training_preparation


def model_directory(directory):
    """Accept the documented deployment layout, retaining old evidence layouts."""
    candidates=[p for p in (directory/'trained',directory) if (p/'model.pt').is_file()]
    if len(candidates)!=1:
        raise ValueError('Require exactly one final model directory')
    return candidates[0]


def finalize(directory,preparation,config):
    trained=model_directory(directory)
    c=json.loads(config.read_text(encoding='utf-8'))
    def path(k):return (ROOT/c['paths'][k]).resolve()
    validate_training_preparation(preparation,path('prepared'),c,path)
    prep=json.loads(preparation.read_text(encoding='utf-8'))
    binding=json.loads((directory/'deployment_binding.json').read_text(encoding='utf-8'))
    receipt=json.loads((directory/'execution_observation.json').read_text(encoding='utf-8-sig'))
    native=json.loads((directory/'native_release/manifest.json').read_text(encoding='utf-8'))
    logs=[json.loads(x) for x in (directory/'training.log').read_text(encoding='utf-8').splitlines() if x.startswith('{')]
    if (receipt['real_exit_code']!=0 or not receipt.get('stdout_completion')
            or [x['epoch'] for x in logs if 'steps' in x]!=list(range(30))
            or binding.get('evaluation_scope')!='strict_tstr'
            or binding.get('dataset_id')!=c['frozen_dataset_id']
            or binding.get('public_slot_count')!=c['train_slots']
            or binding.get('split_binding')!=prep['split_binding']
            or binding.get('preparation_manifest_sha256')!=sha(preparation)
            or native['preparation_manifest_sha256']!=sha(preparation)
            or native['generated_records']!=c['train_slots']
            or native['routes_sha256']!=sha(directory/'native_release/routes.pkl')
            or native['model_sha256']!=sha(trained/'model.pt')
            or native['post_generation_matching'] is not False
            or native['private_input_access_during_generation'] is not False):
        raise ValueError('Incomplete or mismatched train-only execution evidence')
    out=directory/'lineage.json'
    if out.exists():raise FileExistsError(out)
    record=dict(schema='executed_train_only_generation_v1',status='passed',
        generator='MTNet preserved fixed-B DP-SGD and native generator',
        input_policy='train_only_explicit_generator_input',returncode=receipt['real_exit_code'],
        train_sha256=prep['split_binding']['train_sha256'],test_sha256=prep['split_binding']['test_sha256'],
        source_sha256=binding['files']['train_native_mtnet_dpsgd_paper.py'],
        source_files_sha256=binding['files'],dataset_id=c['frozen_dataset_id'],
        public_slot_count=c['train_slots'],epsilon=native['epsilon_training'],delta=native['delta_training'],
        privacy_scope=native['privacy_scope'],preparation_manifest_sha256=sha(preparation),
        execution_observation_sha256=sha(directory/'execution_observation.json'),
        evidence_scope=receipt['evidence_scope'],command=receipt['command'],
        outputs={str(p.relative_to(directory)).replace('\\','/'):sha(p) for p in
                 (directory/'native_release/routes.pkl',directory/'native_release/manifest.json',
                  trained/'model.pt',trained/'paper_algorithm_manifest.json')})
    out.write_text(json.dumps(record,indent=2),encoding='utf-8')
    print('VERIFIED_MTNET_LINEAGE',sha(out))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('directory','preparation','config'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();finalize(a.directory,a.preparation,a.config)
