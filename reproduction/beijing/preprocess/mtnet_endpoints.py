"""Read city-neutral time endpoints keyed by original source record identity."""
import csv
import math


def load_endpoints(filename, source_indices, selected_indices):
    if len(set(source_indices)) != len(source_indices):
        raise ValueError('Repeated frozen source index')
    if len(set(selected_indices)) != len(selected_indices) or any(type(i) is not int or not 0<=i<len(source_indices) for i in selected_indices):
        raise ValueError('Invalid selected population')
    wanted={source_indices[i] for i in selected_indices}
    found={}
    with open(filename, encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            source=int(row['source_index'])
            if source not in wanted: continue
            if source in found: raise ValueError('Repeated endpoint source record')
            start,end=float(row['start_ts']),float(row['end_ts'])
            if not math.isfinite(start) or not math.isfinite(end) or end<start:
                raise ValueError('Invalid endpoint time')
            found[source]=(start,end)
    if set(found)!=wanted: raise ValueError('Missing endpoint source record')
    return [dict(id=slot, start_ts=found[source_indices[i]][0], end_ts=found[source_indices[i]][1],
                 original_source_index=source_indices[i], frozen_population_index=i)
            for slot,i in enumerate(selected_indices,1)]
