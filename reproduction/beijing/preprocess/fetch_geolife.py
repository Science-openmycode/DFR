"""Download the Microsoft archive; validate before extracting. No experiment runs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

URL = 'https://download.microsoft.com/download/f/4/8/f4894aa5-fdbc-481e-9285-d5f8c4c4f039/Geolife%20Trajectories%201.3.zip'


def extract(archive, target):
    target = Path(target).resolve()
    if target.exists():
        raise ValueError('Extraction directory already exists; choose a new directory')
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            path = (target / member.filename).resolve()
            if not path.is_relative_to(target) or '\\' in member.filename or ':' in member.filename:
                raise ValueError('Unsafe archive path: ' + member.filename)
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Archive symlinks are not allowed')
        bad = z.testzip()
        if bad:
            raise ValueError('ZIP CRC failure: ' + bad)
        target.mkdir(parents=True)
        z.extractall(target)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True, help='Download path; existing archives are verified and reused')
    p.add_argument('--extract-to', type=Path, help='New extraction directory (never overwrite)')
    p.add_argument('--expected-sha256', help='Optional checksum supplied by the user; not required to use their data')
    a = p.parse_args()
    if not a.archive.exists():
        a.archive.parent.mkdir(parents=True, exist_ok=True)
        part = a.archive.with_suffix(a.archive.suffix + '.part')
        with part.open('xb') as dst:
            with urllib.request.urlopen(URL, timeout=120) as src:
                shutil.copyfileobj(src, dst)
        with part.open('rb') as f:
            if a.expected_sha256 and hashlib.file_digest(f, 'sha256').hexdigest() != a.expected_sha256.lower():
                raise ValueError('Download checksum mismatch; .part retained for inspection')
        part.rename(a.archive)
    with a.archive.open('rb') as f:
        sha = hashlib.file_digest(f, 'sha256').hexdigest()
    if a.expected_sha256 and sha != a.expected_sha256.lower():
        raise ValueError('Existing archive checksum mismatch; file unchanged')
    if a.extract_to:
        extract(a.archive, a.extract_to)
    print(json.dumps({'url': URL, 'sha256': sha, 'bytes': a.archive.stat().st_size,
                      'extracted_to': str(a.extract_to) if a.extract_to else None}, indent=2))


if __name__ == '__main__':
    main()
