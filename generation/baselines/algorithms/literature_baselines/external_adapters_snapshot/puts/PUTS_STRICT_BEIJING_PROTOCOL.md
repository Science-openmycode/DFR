# PUTS Beijing Strict Protocol

This is the only PUTS protocol in this directory that may be described as an
upstream-code execution.  It separates the map-matching prerequisite from the
published PUTS mechanism.

## What is strict

1. The input subset is raw Beijing GPS only.  No MTR output, MTR candidate,
   private route template, or A* bridge is used.
2. The public OSM cache is filtered to drivable ways and converted to a
   directed FMM network.  FMM writes the connected `cpath`, observation-level
   `opath`, and observation-level matched `pgeom` files expected by PUTS.
3. `run_puts_upstream_unmodified.py` calls the upstream `GlobalDatabase`,
   `SrcDestRegionsSample`, `RoadTransitionMatrix`, `RoadSpeedSample`,
   `RoadSequenceGenerator`, and `TrajectoryPointGenerator` directly.
4. It retains upstream defaults: six regions, five speed bins, `safeValue=1.5`,
   release size equal to the matched training size, and the paper repository's
   `0.33/0.34/0.33` epsilon weights.

## Explicitly retired adapter

`run_puts_same_train_subset.py` is an **obsolete diagnostic only**.  It made
pointwise road snaps and A* bridges, over-drew the release, and replaced the
dense Markov tensor with a disk-backed version.  It must not provide results,
figures, or claims in the paper.

## Reproduce the current Beijing subset

Run from `public_release`:

```powershell
python external_competitors\puts\build_fmm_network_from_public_osm.py `
  --osm-cache data\osm\osm_cache_beijing_drivable_full.pkl `
  --out outputs\external_competitors\puts_beijing_district_quality\public_osm_fmm_full\beijing_drivable_fmm.shp

python external_competitors\puts\prepare_puts_fmm_beijing_subset.py `
  --real outputs\external_competitors\puts_beijing_district_quality\puts_dense_native_fair\accepted_raw_for_fair_comparison.pkl `
  --network outputs\external_competitors\puts_beijing_district_quality\public_osm_fmm_full\beijing_drivable_fmm.shp `
  --out outputs\external_competitors\puts_beijing_district_quality\puts_upstream_fmm_fair `
  --n 451 --overwrite

python external_competitors\puts\run_puts_upstream_unmodified.py `
  --puts-root ..\..\MT_net\PUTS_reproduction\PUTS-main `
  --prepared outputs\external_competitors\puts_beijing_district_quality\puts_upstream_fmm_fair `
  --out outputs\external_competitors\puts_beijing_district_quality\puts_upstream_fmm_fair\upstream_run `
  --epsilon 1.0 --seed 42
```

`prepare_manifest.json` records map-matching eligibility.  For the current
451-trajectory central-Beijing input, 86 trajectories satisfied FMM's matched
and connected-path requirements.  This is a preprocessing attrition result,
not a PUTS performance score; comparisons must use `accepted_raw.pkl` and the
same 86-record release size.
