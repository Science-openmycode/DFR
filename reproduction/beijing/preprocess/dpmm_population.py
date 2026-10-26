"""Select only an already-frozen DPMM input population; never transform records."""
import json
from pathlib import Path


def population_input(prepared, identity, split='full'):
    if split not in ('full','train'):
        raise ValueError('Only full or frozen train is allowed')
    root=Path(prepared).resolve()
    meta=json.loads((root/'canonical_manifest.json').read_text(encoding='utf-8'))
    name='train.pkl' if split=='train' else 'trajectories.pkl'
    count=identity['train_count'] if split=='train' else identity['count']
    return root/name,count,meta['artifacts'][name]


def validation_indices(data, records, exact_records=None):
    import numpy as np
    if exact_records is None:
        return sorted(set(np.linspace(0,len(data)-1,min(records,len(data))).round().astype(int).tolist()) |
                      set(sorted(range(len(data)),key=lambda i:len(data[i]),reverse=True)[:10]))
    if exact_records<60 or exact_records>len(data):
        raise ValueError('Exact validation requires at least 60 available records')
    selected=set(sorted(range(len(data)),key=lambda i:len(data[i]),reverse=True)[:min(10,exact_records)])
    for index in np.linspace(0,len(data)-1,exact_records).round().astype(int).tolist()+list(range(len(data))):
        selected.add(int(index))
        if len(selected)==exact_records:
            break
    return sorted(selected)
