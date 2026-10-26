"""Bind completed historical runs for read-only aggregation in a new checkout."""
import argparse
import gzip
import json
from pathlib import Path
import pickle

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('budget-root','k-root','k-extension','out'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    budget=a.budget_root.resolve();kroot=a.k_root.resolve();extension=a.k_extension.resolve()
    cells=[]
    def add(kind,value,seed,source,post,partition=None):
        native=source/'native/MTR-DFR'
        required=[native.with_name('MTR-DFR.private_audit')/'input_lineage.json',
                  native/f'seed_{seed}_length/road_routes.pkl.gz',
                  post/'representation/route_manifest.json',
                  *[post/stage/'manifest.json' for stage in ('road_scores','physical','coordinate_scores','road_tasks')]]
        if partition is not None:required.append(partition)
        for file in required:
            if not file.is_file():raise FileNotFoundError(file)
        item=dict(kind=kind,value=value,seed=seed,name=source.name,directory=str(source),post_directory=str(post))
        if partition is not None:item['endpoint_partition']=str(partition)
        cells.append(item)
    for value in (.2,.4,.7,1,1.4,2,3):
        for seed in range(20260719,20260724):
            tag=f'eps_{str(value).replace(".","p")}_seed_{seed}'
            add('budget',value,seed,budget/'results'/tag,budget/'post'/tag)
    for value in (24,48,96,192,384,768):
        partition=extension/'nested_partitions'/f'partition{value}.json'
        for seed in range(20260719,20260724):
            tag=f'K{value}_seed_{seed}'
            parent=extension if (extension/'results'/tag).is_dir() else kroot
            source=parent/'results'/tag;post=parent/'post'/tag
            if value==384 and not (source/'native/MTR-DFR.private_audit/input_lineage.json').is_file():
                # The completed K384 control reused the epsilon=1.4 default
                # release. Verify the public partition before recording reuse.
                alias=f'eps_1p4_seed_{seed}'
                cfg=json.loads((budget/'configs'/f'{alias}.json').read_text(encoding='utf-8'))
                if cfg['epsilon']!=1.4:raise ValueError('K384 source has a different privacy budget')
                with gzip.open(cfg['paths']['metric_cache'],'rb') as stream:cache=pickle.load(stream)
                labels=json.loads(partition.read_text(encoding='utf-8'))['labels']
                if {int(n):int(v) for n,v in labels.items()}!=cache['labels384']:
                    raise ValueError('K384 reused source does not use the requested public partition')
                source=budget/'results'/alias;post=budget/'post'/alias
            add('k',value,seed,source,post,partition)
    for value in (96,384,768):
        tag=f'K{value}_seed_20260719_endpoint_exact'
        add('endpoint_diagnostic',value,20260719,extension/'results'/tag,extension/'post'/tag,
            extension/'nested_partitions'/f'partition{value}.json')
    a.out.mkdir(parents=True)
    (a.out/'plan.json').write_text(json.dumps(dict(
        scope='READ_ONLY_COMPLETED_RUN_REPLAY_NOT_NEW_SYNTHESIS',cells=cells),indent=2),encoding='utf-8')
    print(json.dumps(dict(cells=len(cells),budget=35,k=30,endpoint_diagnostic=3,
        new_generation_executed=False,plan=str((a.out/'plan.json').resolve()))))

if __name__=='__main__':main()
