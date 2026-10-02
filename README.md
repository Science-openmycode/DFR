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

## Reviewer supplemental experiments

Completed supplemental evidence is under `experiment_results/rebuttal_supplement/`. The committed CSV/JSON
files and manifests are sufficient to regenerate the four supplement figures without private data:

```powershell
python plotting/plot_rebuttal_supplement.py partition --input experiment_results/rebuttal_supplement/q5_partition_sensitivity/q5_partition_sensitivity_summary.csv --out-dir experiment_results/rebuttal_supplement/figures
python plotting/plot_rebuttal_supplement.py multicity --input-dir experiment_results/rebuttal_supplement/q6_multicity_five_seed --out-dir experiment_results/rebuttal_supplement/figures
python plotting/plot_rebuttal_supplement.py low-epsilon --input-dir experiment_results/rebuttal_supplement/q6_low_epsilon --out-dir experiment_results/rebuttal_supplement/figures
python plotting/plot_rebuttal_supplement.py portal-ablation --input experiment_results/rebuttal_supplement/portal_fiber_ablation/portal_fiber_ablation.csv --out-dir experiment_results/rebuttal_supplement/figures
```

These are supplemental diagnostics, not replacements for the frozen Beijing release. The Oldenburg
500,000-record binaries are intentionally excluded from GitHub; its manifest, metrics, and source
instructions are retained in `experiment_results/rebuttal_supplement/oldenburg_full_scale/`.
