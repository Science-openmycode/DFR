"""Budget plotting entry: current structure metrics and four road applications."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from plotting.render_current_sweeps import render


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--applications', type=Path, required=True,
                   help='Verified four-application sweep summary from README section 08')
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); render('budget', a.source, a.applications, a.out)
