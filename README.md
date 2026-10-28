# MTR-DFR: reproduce the experiments in order

[中文说明](README_CN.md)

MTR-DFR generates synthetic road trajectories from differentially private measurements. Follow the steps below to prepare the Beijing data, generate synthetic datasets, evaluate them, and draw the figures. Synthesis, routing, evaluation, and plotting run as separate stages.

## 1. Download the code

Install [Git LFS](https://git-lfs.com/), then run these commands in PowerShell. The last command opens the experiment directory. Run every subsequent command from this directory.


```powershell
git lfs install
git clone https://github.com/Science-openmycode/DFR.git
cd DFR
git lfs pull
cd reproduction/beijing
```

## 2. Install the Python environment

Use Windows x64 and Python 3.13.9. Install the [Microsoft Visual C++ x64 runtime](https://aka.ms/vs/17/release/vc_redist.x64.exe) and restart if requested. These commands create an environment, install pinned dependencies, and select UTF-8.


```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-clean-windows-py313.txt
.venv/Scripts/python.exe -m pip install -r requirements-torch-cpu-py313.txt
.venv/Scripts/python.exe -m pip check
. .venv/Scripts/Activate.ps1
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
```

## 3. Check the computation environment

The output should end with `CPU_CHECK [2.0, 2.0]`. PrivTrace imports PyTorch, so install the CPU dependencies too. If PowerShell blocks local scripts, inspect `Get-ExecutionPolicy -List`. For a personal account, use `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`; ask your administrator about organization-managed policies.


```powershell
.venv/Scripts/python.exe -c "import sys, torch; print(sys.executable); print(torch.__version__); print('CPU_CHECK', (torch.ones(2)+1).tolist())"
```

## 4. Download the original GeoLife data

The source is [Microsoft GeoLife](https://www.microsoft.com/en-us/download/details.aspx?id=52367). `--archive` selects the ZIP location; `--extract-to` selects a new extraction directory. The output is `data/geolife/Geolife Trajectories 1.3/Data/<user>/Trajectory/*.plt`. Follow the provider's data-use and citation terms.


```powershell
python preprocess/fetch_geolife.py --archive data/downloads/geolife_1.3.zip --extract-to data/geolife
```

## 5. Parse coordinates and timestamps

Filter coordinates to the Beijing bounds, then recover point timestamps and MTNet start/end times. `--bbox` specifies minimum latitude, maximum latitude, minimum longitude, and maximum longitude. This GeoLife input gives 17,123 coordinate trajectories. Road preprocessing creates a separate corpus.


```powershell
python legacy/commands/prepare_geolife_beijing.py --source-dir "data/geolife/Geolife Trajectories 1.3/Data" --out data/raw/real_full_frozen.pkl --seed 20260713 --train-fraction 0.8 --bbox 39.75 40.15 116.10 116.65
python preprocess/recover_raw_metadata.py --source-dir "data/geolife/Geolife Trajectories 1.3/Data" --coordinates data/raw/real_full_frozen.pkl --out data/raw/metadata
python preprocess/prepare_mtnet_time_binding.py --source-dir "data/geolife/Geolife Trajectories 1.3/Data" --reference data/raw/real_full_frozen.pkl --out data/raw/mtnet_time_binding.json
```

## 6. Prepare the public road graph and matching runtime

The public graph is supplied through Git LFS; its license is in `public_assets/BEIJING_FULL_LICENSE.md`. Install Conda before these commands. They create `data/public/network/network.shp`, the OSM cache, and the FMM/STMatch runtime. The environment variables apply to the current terminal.


```powershell
python preprocess/install_public_roads.py --out data/public
conda create --prefix ./data/fmm-runtime --override-channels --channel conda-forge --repodata-fn repodata.json libgdal=2.4.4 boost-cpp=1.75.0 conda-launchers --yes
$env:PATH = "$PWD/data/fmm-runtime/Library/bin;$env:PATH"
$env:GDAL_DATA = "$PWD/data/fmm-runtime/Library/share/gdal"
$env:PROJ_LIB = "$PWD/data/fmm-runtime/Library/share/proj"
```

## 7. Prepare the road trajectory dataset

View the input paths and parameters first. This takes a few seconds:

```powershell
python prepare_roads.py --config configs/preprocess_beijing_8_16.json --out data/road_review --dry-run
```

Start road matching next. The program uses all GPS points, tries 8 road candidates, and retries unsuccessful trajectories with 16 candidates. It uses a 200 m search radius, a 50 m GPS error parameter, and eight threads. It saves the matches and selection report in `data/road_review`. Allow several hours for the full dataset.

```powershell
python prepare_roads.py --config configs/preprocess_beijing_8_16.json --out data/road_review --review-only
```

Open `data/road_review/selection_review.json` to see which trajectories were kept or excluded. After reviewing it, run the command below to create the road dataset from the saved matches, with no further matching. If the second step returns exit code 2, use this command to continue after reading the selection report.

```powershell
python prepare_roads.py --config configs/preprocess_beijing_8_16.json --out data/road_accepted --review-from data/road_review --accept-reviewed-subset yes
```

The completed dataset goes to `data/road_accepted/dataset`. It contains road trajectories, corresponding coordinates, and the training and test splits. This step should take minutes to tens of minutes. Choose a new `--out` directory for each run.

With a `road_review` directory saved by this version, start with the third command. With a complete `dataset` folder, go to the next section and use the same public road network that produced it.

To rescore or redraw figures, use the saved synthetic datasets in `datasets/synthetic/` and experiment results in `reference_results/`.

## 8. Bind a new batch and create its experiment commands

Download MM2, bind inputs and public resources, check the fixed split, build UBODT, and create the batch commands. UBODT needs about 6 GB of disk space. `--batch` names the result namespace; `--threads` controls parallelism. Use new output directories and configuration paths. The final command writes command documents; it does not execute experiments.


```powershell
python preprocess/fetch_mm2.py --archive data/downloads/mm2_1.2.1.zip --extract-to data/mm2_upstream --install-to resources/mm2/map_matching_2.exe
python bind_dataset.py --dataset data/road_accepted/dataset --osm-cache data/public/osm/osm_cache_beijing_drivable_full.pkl --runtime data/fmm-runtime/Library/bin --mm2 resources/mm2/map_matching_2.exe --mm2-network resources/mm2/network --out configs/local_new.json --batch local_new
python prepare_public_resources.py --config configs/local_new.json --frozen-support resources --out-config configs/local_public.json
python prepare_tstr_split.py --config configs/local_public.json --out data/local_split --out-config configs/local_split.json
python prepare_ubodt.py --config configs/local_split.json --out-dir data/local_ubodt --out-config configs/local_ready.json --delta-m 1500 --threads 4
python tools/write_batch_commands.py --config configs/local_ready.json --time-binding data/raw/mtnet_time_binding.json --raw-reference data/raw/real_full_frozen.pkl --out plans/local_new
```

## 9. Run statistical M and R using the generated commands

Open `plans/local_new/commands/reproduction_checked_20261024/COMMANDS_CN.md` and copy each command in order. Each of the four M methods generates full-corpus and training-only outputs, giving eight releases. Apply Origin, Nearest, FMM, STMatch, and MM2-MDP to each, giving 40 routing outputs; then run the full-corpus scoring commands in that document. M writes `measurement.pkl`; R writes coordinates or `synthetic_routes.pkl.gz`. Core routers use M outputs and public road resources; the frozen-batch entry point also checks the dataset directory and split metadata.

## 10. Run DFR, DPMM, and MTNet

Run `plans/local_new/commands/REPRODUCE_DFR_LENGTH_20261024_CN.md`, then `REPRODUCE_NATIVE_BASELINES_20261024_CN.md`. DFR uses `--length-aware` with total ε=1.4. DPMM first runs 60 equivalence comparisons on the current input; record the training-generation exit code as documented. MTNet needs an NVIDIA GPU. Install and check its runtime below, then continue with the documented preparation, export, 30-epoch training, and native generation. Each method retains its own privacy unit and δ.


```powershell
powershell -NoProfile -File deployment/SETUP_MTNET_GPU.ps1 -Root . -BasePython python
.venv/Scripts/python.exe -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0)); print((torch.ones(2, device='cuda')+1).cpu().tolist())"
```

## 11. Evaluate full-corpus utility

Run `plans/local_new/commands/REPRODUCE_NATIVE_SCORES_20261024_CN.md`. DFR and MTNet receive road, coordinate-distribution, physical-structure, and retrospective road-task evaluation. DPMM currently exports coordinate arrays: preserve all output slots, then evaluate coordinate statistics. Metrics requiring absent native road IDs remain missing; no extra matching is added. Each evaluator reads saved synthetic data.

## 12. Run strict TSTR

Run `plans/local_new/commands/REPRODUCE_TSTR_20261024_CN.md`, followed by `REPRODUCE_NATIVE_TSTR_CN.md`. The synthesizer reads only the real training set. Train each downstream model on synthetic training data and evaluate it on the same real test set. Register native-source lineage before deterministic geometry conversion. Each condition writes `results.csv` and `manifest.json`; the model trained on real training data is the common reference.

## 13. Run ablations and privacy attacks

Run the first six sections of the generated `plans/local_new/commands/SUPPLEMENT_COMMANDS.md`: generate and evaluate four algorithm-level ablations, draw the ablation figure, prepare attack inputs for the 23 training releases, run membership attacks, draw their figure, and run the ordered-interface attack. `training_releases.json` points to this batch's outputs. Inapplicable attack cases remain NA. Interpret empirical attacks separately from the mathematical privacy proof.

## 14. Run resolution and privacy-budget experiments

Run `k_COMMANDS_CN.md`, `budget_COMMANDS_CN.md`, and `endpoint_diagnostic_COMMANDS_CN.md` in `plans/local_new/commands/supplement/sweeps/`. K=24/48/96/192/384/768 with five seeds each; ε=0.2/0.4/0.7/1/1.4/2/3 with five seeds each. The three exact-endpoint runs are separate non-private diagnostics. Each run has six stages: generation, representation conversion, road scoring, physical structure, coordinate statistics, and road tasks.

## 15. Aggregate sensitivity results and draw figures

Continue with the three aggregation commands and the budget plotting command in `plans/local_new/commands/SUPPLEMENT_COMMANDS.md`. They read the current configuration and `sweeps_plan.json`, then write batch summaries, per-run CSVs, the budget figure, and the 76-metric appendix. Multi-seed results are research comparisons; compose privacy budgets over actual releases.

## 16. Collect the matrix and generate figures

Finish with `plans/local_new/commands/REPRODUCE_NEW_MATRIX_CN.md` to collect sources from the new score directories and draw the figures. The current frozen specification has 27 rows and 45 columns. Statistical methods have separate M×R entries; DFR, DPMM, and MTNet each have one row. Each cell retains its score source; zero, NA, and missing results have distinct representations. New results go to the batch directory; saved results are in `reference_results/`.

## 17. Small-scale program tests

After installing the runtime, use artificial fixtures to check the interfaces. `SMALL_CLI_CN.md` provides individual small-scale synthesis and routing commands. The commands below run regression tests. Keep fixture outputs separate from dataset-scale experiment results.


```powershell
$env:DFR_TEST_RUNTIME = "$PWD/data/fmm-runtime/Library/bin"
python -m pytest tests -q
```
