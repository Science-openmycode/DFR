# DFR: reproducible MTR-DFR experiments

This repository contains the MTR-DFR implementation, four statistical DP baselines, frozen synthetic releases, evaluation scripts, and figure regeneration code.

## Quick start without private/raw data

The repository includes the synthetic releases and result tables needed to reproduce the packaged experiments and figures:

```powershell
python commands/reproduce.py verify
python commands/reproduce.py smoke
python commands/reproduce.py all-precomputed
```

Expected output includes `VERIFY OK`, `smoke: OK`, and PNG/PDF files under `experiment_results/regenerated_figures/`.

## From-scratch reproduction

The exact Beijing release requires external materials that cannot be redistributed here:

- Microsoft GeoLife GPS Trajectories 1.3 `.plt` files;
- the public Beijing road Shapefile (`.shp`, `.dbf`, `.shx`, `.prj`);
- the FMM/UBODT and STMatch binaries;
- Windows GDAL 2.4.4 and Boost.Serialization 1.75.0 runtime DLLs.

The Chinese guide [`README_CN.md`](README_CN.md) gives the official download links, every preparation command, all required parameters, expected output paths, and the complete order for framework, privacy, profile, M×R, ablation, strict TSTR, and physical-structure experiments. `docs/COMMAND_PARAMETERS_CN.md` documents the meaning of every command-line parameter. Without the external GeoLife files, the packaged releases and all packaged figures remain reproducible, but new Beijing synthetic releases cannot be regenerated from raw data.

On Windows, the tested matcher runtime is created with:

```powershell
conda create --prefix "C:\fmm-runtime" --override-channels --channel conda-forge --repodata-fn repodata.json libgdal=2.4.4 boost-cpp=1.75.0 --yes
```

Then follow the `PATH`, `GDAL_DATA`, `PROJ_LIB`, `verify-matcher`, and `prepare-road-reference` commands in `README_CN.md`. Do not substitute a different road graph for the frozen Beijing results without recording its SHA-256 in the run manifest.

## DFR resolution and privacy-budget sweeps

The DFR generator exposes two research parameters independent of the legacy GSRT Q5 batch. `--resolution-k` controls the number of private fine endpoint cells retained per endpoint role; the public road graph, routing support, and fixed output slots do not change. Omitting it keeps the frozen value `K=8`. `--epsilon-total` proportionally rescales the frozen measurement-block allocation and records the composed budget in `manifest.json` (including the length block when `--length-aware` is enabled). For example:

```powershell
python commands/reproduce.py generate-main -- --real-matched "C:\runs\real_road_reference\matched_paths\Real.pkl.gz" --edge-cache "public_assets\ordered_portal_route_cache.pkl.gz" --network "public_assets\beijing_network\network.shp" --seed 20260719 --length-aware --resolution-k 16 --epsilon-total 0.4 --public-slot-count 17123 --out-dir "C:\runs\dfr_k16_eps04"
```

Each point writes `road_routes.pkl.gz`, `dp_transcript.pkl.gz`, `manifest.json`, and `input_lineage.json`. Vary `--resolution-k` (for example `2,4,8,16,32,64`) or `--epsilon-total` (for example `0.2,0.4,0.7,1.0,1.4,2.0,3.0`) with a fresh output directory for every point.
