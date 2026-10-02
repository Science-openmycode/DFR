# Reproduced Published Methods

This directory contains the public-release implementations of the published
trajectory synthesis baselines used by the paper.

## Directory Map

| Method | Code directory | Current status |
|---|---|---|
| SPRT | `SPRT/` | Paper-structured reproduction. Author code and original Didi/Ucar data are unavailable. |
| PrivTrace | `PrivTrace/` | Official-generator-assisted reproduction for the original metric audit; local implementation for full-release migration. |
| DPTraj-PM | `DPTrajPM/` | Author-code baseline verified on bundled package data for the Stage-A original-metric audit. |
| DPStd | `DPStd/` | Paper-structured reproduction. The best faithful run partially matches the original metric scale but is not Table-3 certified. |
| Shared utilities | `common/` | Evaluation and road-adapter utilities. |

## Run Through the Public Entry Point

Do not run the method files directly for paper experiments. Use the public
pipeline entry point from the `public_release` directory:

```powershell
python synthesize_dataset.py `
  --method sprt-native `
  --data geolife `
  --osm-cache data\osm\osm_cache_beijing.pkl `
  --epsilon 1.0 `
  --out-dir outputs\synthetic_releases `
  --tag geolife_sprt_native_full
```

The method names are:

```text
sprt-native
sprt-osm
privtrace-native
privtrace-osm
dptrajpm-native
dptrajpm-osm
dpstd-native
dpstd-osm
```

The `*-native` variants are the published-method reproductions. The `*-osm`
variants are explicitly baseline-plus-public-road-adapter diagnostics. They are
useful for isolating output-domain effects, but they must not be described as
the original published algorithms.

## Certification Boundary

Use `check/baseline_reproduction_registry.json` and
`check/STAGE_A_BASELINE_CERTIFICATION_20260708.md` as the source of truth for
which reproductions are certified against original-paper metrics.

Excluded diagnostic files such as SPRT trajectory templates, DPStd trajectory
pools and PRA adapters have been moved out of the
main `check/` layer into:

```text
legacy/excluded_native_baseline_diagnostics_20260709/check/
```

Those files explain why stronger geometry support can repair visuals, but they
are not faithful native baseline implementations.
