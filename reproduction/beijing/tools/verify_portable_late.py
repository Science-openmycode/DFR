"""Check only the newly bundled plotting and K imports under relocated paths."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pickle
import sys

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--forbid-workspace',type=Path,required=True)
    p.add_argument('--allow-environment',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    a.forbid_workspace=a.forbid_workspace.resolve();a.allow_environment=a.allow_environment.resolve()
    def guard(event,args):
        if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
            path=Path(os.fsdecode(args[0])).resolve()
            if path.is_relative_to(a.forbid_workspace) and not path.is_relative_to(ROOT) and not path.is_relative_to(a.allow_environment):
                raise RuntimeError('External project access: '+str(path))
    sys.addaudithook(guard);sys.path.insert(0,str(ROOT))
    sys.path[:0]=[str(ROOT/'legacy/evaluation'),str(ROOT/'legacy/generation/mtr_dfr/algorithm'),
                  str(ROOT/'legacy/generation/mtr_dfr/dependencies'),str(ROOT/'repairs/k_partition_20261020/algorithm')]
    from endpoint_partition import load_partition
    with gzip.open(ROOT/'resources/metric_cache/metric_cache.pkl.gz','rb') as f:cache=pickle.load(f)
    partitions=[]
    for k in [24,48,96,192,384,768]:
        _,actual,binding=load_partition(ROOT/f'resources/endpoint_partitions/partition{k}.json',cache,
            network=ROOT/'resources/network/network.shp',metric_cache=ROOT/'resources/metric_cache/metric_cache.pkl.gz')
        assert actual==k;partitions.append(binding)
    modules=[]
    for name,rel in [('k_core','repairs/k_partition_20261020/algorithm/run_minimal_strong_family.py'),
                     ('diagnostic','supplement/k_original/diagnostic_core.py'),
                     ('original_plot','legacy/plotting/regenerate_figures.py')]:
        spec=importlib.util.spec_from_file_location(name,ROOT/rel);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        modules.append(rel)
    from tools.audit_readme_commands import probe
    from tools.check_documented_command import check
    doc=ROOT/'SUPPLEMENT_COMMANDS_CN.md';digest=hashlib.sha256(doc.read_bytes()).hexdigest();count=0
    for i,line in enumerate(doc.read_text(encoding='utf-8').splitlines(),1):
        if line.startswith('.venv/Scripts/python.exe '):check(doc,i,line,digest);probe(line);count+=1
    result={'status':'PASSED','root':str(ROOT),'external_workspace_reads':'denied except interpreter environment',
            'partitions':partitions,'actual_modules_imported':modules,'additional_commands':count,'experiments_repeated':0}
    a.out.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({'status':'PASSED','partitions':len(partitions),'commands':count}))


if __name__=='__main__':main()
