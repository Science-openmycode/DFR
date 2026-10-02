# DFR algorithm-level ablation

The result table in this directory was generated on the cloud reproduction host from the public DFR entry point with seed `20260723`, epsilon `1.15`, length-aware reconstruction, and 17,123 fixed output slots. The four arms are synthesized from the same matched Beijing input:

- `no-endpoint-measurement`: public endpoint carrier only;
- `endpoint-measurement-only`: private endpoint measurement and public routing;
- `family-measured-unmatched-router`: family transcript measured but not consumed by the matched router;
- `full`: the complete DFR measurement and family-guided routing pipeline.

`results.csv` reports the complete route-utility metric set used by DFR. `summary_manifest.json` records the arm hashes, protocol, seeds, epsilon, slot count, and the SHA-256 of the result table. The saved arm route files remain on the reproduction host because they are large; the table and hashes are sufficient to identify the released run.

To regenerate the four arms from a local matched input, run:

```powershell
python evaluation/run_ablation_experiment.py `
  --out-dir experiment_results/ablation/run `
  --data <real_full_frozen.pkl> `
  --real-routes <Real.pkl.gz> `
  --edge-cache public_assets/ordered_portal_route_cache.pkl.gz `
  --network public_assets/beijing_network/network.shp `
  --epsilon-total 1.15 `
  --noise-seed 20260723 `
  --decoder-seed 30260723 `
  --request-seed 40260723 `
  --public-slot-count 17123 `
  --length-aware `
  --variants no-endpoint-measurement endpoint-measurement-only family-measured-unmatched-router full
```
