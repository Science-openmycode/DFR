"""Read-only hash audit of completed documented coordinate evaluations; no evaluation."""
import hashlib
import json
from pathlib import Path


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    root = Path.cwd()
    document = root / 'SERVER_REMAINING_COMMANDS_20261017_CN.md'
    docsha = sha(document)
    lines = document.read_text(encoding='utf-8').splitlines()
    assert docsha == 'b0db6228622cd74c8d8c44f55db5cd473d67c59ce696719c8bc39c935a1286e2'
    records = [json.loads(row) for row in (root/'outer_execution_ledger.jsonl').read_text(encoding='utf-8-sig').splitlines() if row.strip()]
    completed = {}
    for record in records:
        if record['phase'] == 'finish' and record['exit_code'] == 0:
            assert record['actual_outer_command'] == lines[record['line']-1]
            assert record['document_sha256'] == docsha
            completed[record['line']] = record
    assert set(completed) == set(range(18, 31))
    report = []
    for number, receipt in sorted(completed.items()):
        args = receipt['actual_outer_command'].split()
        method = args[args.index('--method')+1]
        router = args[args.index('--router')+1]
        out = root/'data_results/simple_runs/roads_8_16_20261016/coordinate_scores_audit_v2'/method/router
        for name, expected in receipt['outputs_sha256'].items():
            assert sha(out/name) == expected, (method, router, name)
        manifest = json.loads((out/'manifest.json').read_text(encoding='utf-8'))
        revision = json.loads((out/'metric_revision.json').read_text(encoding='utf-8'))
        assert revision['protocol'] == 'metric-audit-v2-20261016'
        assert manifest['inputs']['real']['count'] == 15730
        bindings = 0
        for name, info in manifest['inputs'].items():
            if info is not None:
                assert sha(info['path']) == info['sha256'], (method, router, name)
                bindings += 1
        for name, expected in manifest['outputs'].items():
            assert sha(out/name) == expected, (method, router, name)
        for name, expected in revision['source_sha256'].items():
            assert sha(name) == expected, (method, router, name)
        report.append(dict(method=method, router=router, line=number, seconds=receipt['seconds'], input_hashes=bindings, source_hashes=len(revision['source_sha256']), outputs_sha256=receipt['outputs_sha256']))
    print(json.dumps(dict(verified=True, count=len(report), document_sha256=docsha, cells=report), ensure_ascii=False))


if __name__ == '__main__':
    main()
