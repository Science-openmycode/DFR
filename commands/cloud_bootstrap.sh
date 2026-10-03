#!/usr/bin/env bash
set -euo pipefail

# Reproduce the public DFR repository on a clean Linux GPU host.
# Usage: bash commands/cloud_bootstrap.sh [workdir]
WORKDIR="${1:-$PWD/DFR_cloud}"
REPO_URL="https://github.com/Science-openmycode/DFR.git"

mkdir -p "$(dirname "$WORKDIR")"
if [[ ! -d "$WORKDIR/.git" ]]; then
  git lfs install --skip-repo
  git clone "$REPO_URL" "$WORKDIR"
fi
cd "$WORKDIR"
git lfs pull

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-lock.txt

python commands/reproduce.py verify
python commands/reproduce.py smoke
echo "DFR cloud bootstrap completed in $WORKDIR"
echo "Run packaged experiment checks with: python commands/reproduce.py all-precomputed"
echo "Run a fresh Beijing release only after supplying the external GeoLife and road assets documented in README_CN.md."
