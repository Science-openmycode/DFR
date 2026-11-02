"""Bind user-selected prepared resources and releases without editing Python."""
import argparse
import os
from pathlib import Path
from .metrics import read, digest
from .engine import write


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--questions', type=Path, required=True); p.add_argument('--region', type=Path, required=True)
    p.add_argument('--public-edges', type=Path, required=True); p.add_argument('--real-slots', type=Path, required=True)
    p.add_argument('--release', action='append', default=[], help='NAME=slots.jsonl.gz; repeat for each method')
    p.add_argument('--slots', type=int, required=True); p.add_argument('--resources', type=Path, required=True)
    p.add_argument('--coverage-distance-m', type=float, default=40); p.add_argument('--route-budget-m', type=float, default=4437.46)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); q = read(a.questions)
    if q['status'] != 'LOCKED_REAL_ONLY' or a.slots < 1 or a.coverage_distance_m <= 0 or a.route_budget_m <= 0:
        raise ValueError('Invalid question lock, population or public parameters')
    if q['representative']['distance_m'] != a.coverage_distance_m:
        raise ValueError('Coverage distance differs from frozen questions')
    def rel(path):
        try: return os.path.relpath(path.resolve(), a.out.resolve().parent).replace('\\', '/')
        except ValueError: return str(path.resolve())
    methods = [dict(name='Real', slots=rel(a.real_slots), sha256=digest(a.real_slots))]
    for value in a.release:
        name, source = value.split('=', 1)
        if not name or name in {x['name'] for x in methods}:
            raise ValueError('Duplicate/reserved/empty method name')
        methods.append(dict(name=name, slots=rel(Path(source)), sha256=digest(source)))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    write(a.out, dict(dataset_id=q['dataset_id'], slots=a.slots, real_method='Real', coordinate_units='metre',
          public_edges=rel(a.public_edges), questions=rel(a.questions), region=rel(a.region), resources=rel(a.resources),
          coverage_distance_m=a.coverage_distance_m, route_budget_m=a.route_budget_m, methods=methods))
    print('CONFIGURED', len(methods), 'conditions', a.out, flush=True)


if __name__ == '__main__': main()
