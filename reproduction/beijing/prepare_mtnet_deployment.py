"""Export prepared MTNet inputs and unchanged model/trainer to the second machine."""
import argparse
import json
from pathlib import Path
import shutil
import zipfile

from preprocess.dataset_contract import sha


def deployment_population(meta, train_only=False):
    count=meta['input_count']
    full_count=meta.get('full_population_count',count)
    if (type(count) is not int or type(full_count) is not int or count<10
            or full_count<count or meta['original_loader_counts'].get('trainable',0)<10):
        raise ValueError('Wrong or insufficient frozen MTNet inputs')
    if train_only:
        split=meta.get('split_binding',{})
        indices=meta.get('selected_frozen_indices',[])
        if (meta.get('evaluation_scope')!='strict_tstr'
                or len(indices)!=count or len(set(indices))!=count
                or any(type(i) is not int or i<0 or i>=full_count for i in indices)
                or not all(split.get(k) for k in ('split_audit_sha256','train_sha256','test_sha256','train_indices_sha256'))
                or meta.get('input_sha256')!=split['train_sha256']):
            raise ValueError('Training-only input lacks frozen split binding')
    elif meta.get('evaluation_scope','full_corpus')!='full_corpus' or count!=full_count:
        raise ValueError('Do not deploy a training release as full-corpus')
    return count


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--original-root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--train-only',action='store_true')
    a=p.parse_args()
    if a.out.exists() or a.archive.exists():raise FileExistsError('Choose new deployment paths')
    source_root=(a.original_root/'official').resolve()
    lock=json.loads((a.original_root/'canonical_mtnet_source_lock.json').read_text(encoding='utf-8'))
    source_files=lock.get('files_sha256',{})
    if not {'mtnet.py','train.py','util/config.py'} <= set(source_files):
        raise ValueError('Incomplete MTNet source lock')
    for name,digest in source_files.items():
        source=(source_root/name).resolve()
        if not source.is_relative_to(source_root) or sha(source)!=str(digest).lower():
            raise ValueError('MTNet source lock changed: '+name)
    meta=json.loads((a.prepared/'full_preparation_manifest.json').read_text(encoding='utf-8'))
    population=deployment_population(meta,a.train_only)
    for name,digest in meta['data_files_sha256'].items():
        file=(a.prepared/'data/beijing_roads_l20'/name).resolve()
        if file.parent!=(a.prepared/'data/beijing_roads_l20').resolve() or sha(file)!=digest:
            raise ValueError('Prepared input changed: '+name)
    a.out.mkdir(parents=True)
    files={}
    def copy(source,relative):
        dest=a.out/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,dest);files[str(relative).replace('\\','/')]=sha(dest)
    for file in (a.original_root/'official').rglob('*.py'):
        copy(file,Path('official')/file.relative_to(a.original_root/'official'))
    for name in ('canonical_mtnet_source_lock.json','train_native_mtnet_dpsgd_paper.py'):
        copy(a.original_root/name,name)
    for name in ('full_preparation_manifest.json','public_origin_ids.npy'):
        copy(a.prepared/name,name)
    for file in (a.prepared/'data/beijing_roads_l20').iterdir():
        if file.is_file():copy(file,Path('data/beijing_roads_l20')/file.name)
    copy(Path(__file__).with_name('generate_mtnet.py'),'generate_mtnet.py')
    copy(Path(__file__).parent/'deployment/RUN_MTNET_GPU.ps1','RUN_MTNET_GPU.ps1')
    for name in ('RUN_MTNET_GPU_RESUME.ps1','SETUP_MTNET_GPU.ps1','NativeArguments.ps1','configure_windows_runtime.py'):
        copy(Path(__file__).parent/'deployment'/name,name)
    # Windows VC runtime is installed by the user as described in README.
    # The export does not depend on a historical machine's private DLL bundle.
    copy(Path(__file__).parent/'requirements-clean-windows-py313.txt','requirements-clean-windows-py313.txt')
    copy(Path(__file__).parent/'requirements-gpu-windows-py313.txt','requirements-gpu-windows-py313.txt')
    (a.out/'deployment_binding.json').write_text(json.dumps(dict(files=files,
        dataset_id=meta['dataset_id'],input_count=population,public_slot_count=population,
        evaluation_scope='strict_tstr' if a.train_only else 'full_corpus',
        split_binding=meta.get('split_binding',{}),
        preparation_manifest_sha256=sha(a.prepared/'full_preparation_manifest.json'),
        training_count=meta['original_loader_counts']['trainable']),indent=2),encoding='utf-8')
    with zipfile.ZipFile(a.archive,'x',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for file in sorted(a.out.rglob('*')):
            if file.is_file():z.write(file,file.relative_to(a.out))
    print('MTNET_DEPLOYMENT',a.archive.stat().st_size,sha(a.archive))


if __name__=='__main__':main()
