"""Fetch the exact upstream MM2 release, retaining its bundled license notices."""
import argparse
import hashlib
from pathlib import Path
import shutil
import urllib.request
from fetch_geolife import extract

URL='https://github.com/addy90/map-matching-2/releases/download/v1.2.1/map_matching_2-1.2.1-win64.zip'
ARCHIVE_SHA='d431897bd3ac67a138ac97228ea6d7897e31f26f8e07038480d9f7b9149b6b02'
EXE_SHA='21669275ade3858a63801baa58a413084016f011a7ec553f93c20389425d78d1'
def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True)
    p.add_argument('--extract-to',type=Path,required=True,help='New directory retaining upstream bin/ and doc/')
    p.add_argument('--install-to',type=Path,required=True,help='Exact executable destination; never overwrite different bytes')
    a=p.parse_args()
    if not a.archive.exists():
        a.archive.parent.mkdir(parents=True,exist_ok=True)
        part=a.archive.with_suffix('.part')
        with part.open('xb') as f,urllib.request.urlopen(URL,timeout=120) as src:shutil.copyfileobj(src,f)
        if digest(part)!=ARCHIVE_SHA:raise ValueError('Download differs from frozen version')
        part.rename(a.archive)
    if digest(a.archive)!=ARCHIVE_SHA:raise ValueError('Archive mismatch')
    extract(a.archive,a.extract_to)
    exe=a.extract_to/'bin/map_matching_2.exe'
    if digest(exe)!=EXE_SHA:raise ValueError('Executable mismatch')
    a.install_to.parent.mkdir(parents=True,exist_ok=True)
    if a.install_to.exists():
        if digest(a.install_to)!=EXE_SHA:raise FileExistsError(a.install_to)
    else:shutil.copy2(exe,a.install_to)
    print('VERIFIED_MM2_1.2.1',a.install_to)
if __name__=='__main__':main()
