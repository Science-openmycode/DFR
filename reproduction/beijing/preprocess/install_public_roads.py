"""Install only the public OSM snapshot shipped with this repository."""
import argparse
import hashlib
from pathlib import Path
from fetch_geolife import extract

SHA256 = 'cac4f6fa91a80ad59c2c5570cb7c31e972ed90b1bae0fd70d2dbc68f4731cd60'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,default=Path(__file__).resolve().parents[3]/'public_assets/beijing_full_20261026.zip')
    p.add_argument('--out',type=Path,required=True,help='New directory; contains network/ and osm/')
    a=p.parse_args()
    with a.archive.open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest()!=SHA256:
            raise ValueError('Public road archive mismatch; fetch the actual repository asset')
    extract(a.archive,a.out)
    print('Public graph installed at '+str(a.out.resolve()))

if __name__=='__main__':main()
