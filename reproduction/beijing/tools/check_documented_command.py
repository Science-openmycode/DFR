"""Compare an outer command verbatim with a frozen document line; never execute it."""
import argparse
import hashlib
from pathlib import Path


def check(document, line_number, actual, expected_document_sha256):
    raw=Path(document).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_document_sha256:
        raise ValueError('Document changed; re-review the plan before running')
    lines=raw.decode('utf-8-sig').splitlines()
    if not 1<=line_number<=len(lines):raise ValueError('Invalid document line')
    expected=lines[line_number-1]
    inside=False
    for line in lines[:line_number-1]:
        if line.startswith('```'):inside=not inside
    if not inside or not expected or expected.lstrip().startswith(('#','```')):
        raise ValueError('Select an actual command line inside a code block')
    if '\n' in actual or '\r' in actual:
        raise ValueError('Only one explicit outer command is allowed')
    if actual!=expected:
        raise ValueError('Outer command is not verbatim identical; do not run a replacement entrypoint')
    if any(token in expected for token in ('<M>','<R>','<arm>','<method>','<dataset>')):
        raise ValueError('Unexpanded template; document the concrete command before running')
    return expected


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--document',type=Path,required=True)
    parser.add_argument('--line',type=int,required=True)
    parser.add_argument('--document-sha256',required=True)
    parser.add_argument('--actual-command',required=True)
    a=parser.parse_args()
    check(a.document,a.line,a.actual_command,a.document_sha256)
    print('VERBATIM_MATCH_ONLY: preflight passed; no experiment was executed')


if __name__=='__main__':main()
