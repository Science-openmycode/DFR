"""Read-only command/interface audit: stops at argparse, never runs experiments."""
import argparse
import contextlib
import ctypes
import hashlib
import io
import json
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.check_documented_command import check


def split_windows(command):
    count = ctypes.c_int()
    split = ctypes.windll.shell32.CommandLineToArgvW
    split.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
    split.restype = ctypes.POINTER(ctypes.c_wchar_p)
    pointer = split(command, ctypes.byref(count))
    if not pointer:
        raise ValueError('Cannot parse Windows command')
    try:
        return [pointer[i] for i in range(count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(pointer, ctypes.c_void_p))


class Parsed(BaseException):
    pass


def portable_argument(value):
    if isinstance(value,Path):return str(value)
    if isinstance(value,list):return [portable_argument(v) for v in value]
    if isinstance(value,dict):return {k:portable_argument(v) for k,v in value.items()}
    return value


def probe(command):
    argv = split_windows(command)
    script = ROOT / argv[1]
    if not (ROOT / argv[0]).is_file() or not script.is_file():
        raise FileNotFoundError('Interpreter or script missing')
    original, previous = argparse.ArgumentParser.parse_args, sys.argv
    previous_path=sys.path[:]
    captured = {}
    def intercept(parser, *args, **kwargs):
        namespace = original(parser, *args, **kwargs)
        captured.update(vars(namespace))
        raise Parsed()
    log = io.StringIO()
    try:
        argparse.ArgumentParser.parse_args = intercept
        sys.path.insert(0,str(script.parent))
        sys.argv = argv[1:]
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                runpy.run_path(str(script), run_name='__main__')
            except Parsed:
                return {'status': 'ARGUMENTS_ACCEPTED_NOT_EXECUTED', 'script': str(script),
                        'arguments': portable_argument(captured)}
            except SystemExit as exc:
                raise ValueError(f'Parser exit {exc.code}: {log.getvalue()}') from exc
        raise ValueError('Expected argparse interception was not reached')
    finally:
        argparse.ArgumentParser.parse_args, sys.argv = original, previous
        sys.path[:]=previous_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--runbook', type=Path, default=ROOT/'reproduction_20261024')
    parser.add_argument('--supplement', type=Path, action='append', default=[], help='Audit only new command documents; do not repeat the previous runbook audit')
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    if args.supplement:
        rows=[]
        for doc in args.supplement:
            digest=hashlib.sha256(doc.read_bytes()).hexdigest()
            for number,line in enumerate(doc.read_text(encoding='utf-8').splitlines(),1):
                if line.startswith('.venv/Scripts/python.exe '):
                    check(doc,number,line,digest)
                    rows.append({'document':str(doc),'document_sha256':digest,'document_line':number,**probe(line)})
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps({'scope':'Additional Python command parser audit only; PowerShell training not executed', 'experiment_executed':False,'commands_checked':len(rows),'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'commands_checked':len(rows),'experiment_executed':False}))
        return
    folder = args.runbook
    manifest = json.loads((folder/'commands.json').read_text(encoding='utf-8'))
    doc = folder/'COMMANDS_CN.md'
    rows, known = [], set()
    actual_digest = hashlib.sha256(doc.read_bytes()).hexdigest()
    doc_binding = {'recorded': manifest['document_sha256'], 'actual': actual_digest,
                   'matches': actual_digest == manifest['document_sha256'],
                   'matches_lf_normalized': hashlib.sha256(doc.read_text(encoding='utf-8').encode()).hexdigest() == manifest['document_sha256']}
    for step in manifest['steps']:
        # Audit the current exact document while preserving the stale-binding finding.
        check(doc, step['document_line'], step['command'], actual_digest)
        if not set(step['depends_on']) <= known:
            raise ValueError('Dependency order invalid: '+step['id'])
        result = probe(step['command'])
        rows.append({'id': step['id'], 'document_line': step['document_line'], **result})
        known.add(step['id'])
    for name in ('REPRODUCE_DFR_LENGTH_20261024_CN.md', 'REPRODUCE_NATIVE_SCORES_20261024_CN.md'):
        path = ROOT/name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            if line.startswith('.venv/Scripts/python.exe '):
                check(path, number, line, digest)
                rows.append({'id': name, 'document_line': number, **probe(line)})
    payload = {'scope': 'Verbatim lines, dependency order, interpreter/script presence and actual argparse acceptance only',
               'experiment_executed': False, 'document_binding': doc_binding,
               'commands_checked': len(rows), 'rows': rows}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'commands_checked': len(rows), 'experiment_executed': False}))


if __name__ == '__main__':
    main()
