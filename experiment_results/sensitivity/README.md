# DFR sensitivity results

This directory contains the completed Beijing DFR sensitivity runs produced from the public DFR entry point.

- `dfr_sensitivity_summary.csv` contains the unified metrics for six resolution settings (`K=2,4,8,16,32,64`) and seven privacy budgets (`epsilon=0.2,0.4,0.7,1.0,1.4,2.0,3.0`). Each row records the sweep type, parameter, seed, metric, value, and the source manifest.
- `dfr_sensitivity_manifests.json` records the 13 source manifests, their SHA-256 values, composed privacy parameters, fixed output slots, input size, runtime, and route/transcript hashes.

All runs use the same Beijing frozen input, public directed road graph, edge cache, 17,123 output slots, coordinate conversion, and unified profile evaluator. The resolution sweep uses seed `20260721`; the privacy-budget sweep uses seed `20260722`. The budget sweep is a research sensitivity study and is not a collection of simultaneous formal releases.

To reproduce one point, use `commands/reproduce.py generate-main` with a fresh `--out-dir`, then run `routes-to-coordinates` and `run-profile` as described in the repository README. The `resolution_k` and `epsilon_total` values are recorded in each generated `manifest.json`.
