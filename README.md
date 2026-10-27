# MTR-DFR

[中文说明](README_CN.md)

MTR-DFR generates synthetic road trajectories from differentially private measurements. This repository includes the algorithm, baseline implementations, evaluation tools, saved synthetic datasets, and plotting code.

The steps below generate synthetic datasets, reconstruct road trajectories, evaluate their utility, and produce the experiment figures. Each stage writes its own outputs, so you can generate a dataset on one machine and run its routing or evaluation on another.

## Download the code

Install [Git LFS](https://git-lfs.com/), then open PowerShell and run:

```powershell
git lfs install
git clone https://github.com/Science-openmycode/DFR.git
cd DFR
git lfs pull
cd reproduction/beijing
```

Run all commands below from `DFR/reproduction/beijing`. Paths in commands are relative to that directory.

## 1. Install the environment

Use Windows x64 with Python 3.13.9. Install the [Microsoft Visual C++ x64 runtime](https://aka.ms/vs/17/release/vc_redist.x64.exe) and restart Windows if the installer requests it. Then open PowerShell in this directory:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-clean-windows-py313.txt
.venv/Scripts/python.exe -m pip install -r requirements-torch-cpu-py313.txt
.venv/Scripts/python.exe -m pip check
. .venv/Scripts/Activate.ps1
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
```

These commands create a local environment and install the pinned Python packages, including CPU PyTorch for PrivTrace. Check that PyTorch can compute:

```powershell
.venv/Scripts/python.exe -c "import sys, torch; print(sys.executable); print('torch', torch.__version__); print('CPU_CHECK', (torch.ones(2)+1).tolist())"
```

The output ends with `CPU_CHECK [2.0, 2.0]`. Install the FMM/STMatch runtime using the commands in [Data preparation](reproduction/beijing/DATA.md#4-prepare-the-road-matching-runtime).

If PowerShell blocks local scripts, inspect `Get-ExecutionPolicy -List`. For a personal account, you can enable local scripts with `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`. Organization-managed policies need your administrator. You can also invoke Python as `.venv/Scripts/python.exe` without activating the environment.

### MTNet GPU environment

MTNet training uses an NVIDIA GPU and a compatible driver. Install its pinned CUDA packages before training:

```powershell
powershell -NoProfile -File deployment/SETUP_MTNET_GPU.ps1 -Root . -BasePython python
.venv/Scripts/python.exe -c "import torch; assert torch.cuda.is_available(), 'CUDA unavailable'; x=torch.ones(2, device='cuda'); print(torch.cuda.get_device_name(0)); print('GPU_CHECK', (x+1).cpu().tolist())"
```

The setup script writes installation logs to `setup_logs/`. The second command prints the GPU name and `GPU_CHECK [2.0, 2.0]`.

## 2. Prepare the data

Follow [Data download and preprocessing](reproduction/beijing/DATA.md). It covers the official GeoLife download, coordinate parsing, timestamp recovery, the supplied public road graph, and road matching. The final step creates commands for your new batch in `plans/local_new/commands/`.

The historical road-level batch contains 15,730 trajectories. Its strict TSTR split has 12,584 training and 3,146 test trajectories. The earlier coordinate-level batch contains 17,123 trajectories. Each batch has its own configuration and output namespace.

Use the command lists generated for your batch when starting from downloaded data. The command lists linked below describe the saved road-level batch. An optional `import_external_assets.py` utility imports a research snapshot you already have; the download-and-preprocess route starts from the original data.

## 3. Experiment order

### Statistical synthesis and road reconstruction

Run the commands in [Statistical M, routing, and evaluation](reproduction/beijing/reproduction_checked_20261024/COMMANDS_CN.md), or their counterparts in your generated batch plan.

- Generate full-corpus and training-only synthetic coordinates with SPRT, PrivTrace, DPTraj-PM, and DPStd. This produces eight M outputs.
- Apply Origin, Nearest, FMM, STMatch, and MM2-MDP to each M output. This produces 40 routed outputs. Routers read the published synthetic coordinates and public road resources.
- Evaluate the full-corpus outputs with the coordinate, road, physical-structure, and road-task evaluators.

Generation writes each method's `measurement.pkl` and manifest. Routing writes synthetic coordinates or `synthetic_routes.pkl.gz`. Evaluation writes named metric files and manifests. You can reuse an existing M output with another router without repeating synthesis.

### Native road generators

Follow [MTR-DFR generation](reproduction/beijing/REPRODUCE_DFR_LENGTH_20261024_CN.md), then [Native road evaluation](reproduction/beijing/REPRODUCE_NATIVE_SCORES_20261024_CN.md). The experiment configuration uses `--length-aware` and a total privacy budget of epsilon=1.4. DFR writes `road_routes.pkl.gz` with the configured public output count. Length recovery shares this total budget.

[DPMM and MTNet commands](reproduction/beijing/REPRODUCE_NATIVE_BASELINES_20261024_CN.md) cover full-corpus and training-only generation. DPMM uses the accelerated implementation; MTNet prepares the author's input format, trains the model, and generates native road trajectories.

MTR-DFR, DPMM, and MTNet each contribute one native result per metric. Score their road output using deterministic identifier/geometry conversion. Their native output is used as generated, rather than being passed through another map matcher. Each method retains its stated privacy unit and delta.

### Strict TSTR downstream tasks

Use the [Statistical M×R TSTR commands](reproduction/beijing/REPRODUCE_TSTR_20261024_CN.md) and [Native TSTR commands](reproduction/beijing/REPRODUCE_NATIVE_TSTR_CN.md).

Fit each synthesizer on the real training split and generate synthetic training data. Train the downstream model on that synthetic data, then evaluate it on the same real test split used for the real-trained reference. This compares the two training sources on a common test population. Road identifiers are converted to their fixed geometries for coordinate-based tasks.

The outputs include downstream task scores, release lineage, and plots. [Supplementary commands, section 1](reproduction/beijing/SUPPLEMENT_COMMANDS_CN.md) also provides scoring and plotting commands for the saved 23-condition TSTR inputs.

### Privacy attacks and component ablations

[Supplementary commands, sections 2–3](reproduction/beijing/SUPPLEMENT_COMMANDS_CN.md) run the membership and ordered-interface attacks, then four algorithm-level ablations. For each ablation, run generation and evaluation before plotting its score CSV. Empirical attacks assess the tested attack models; the mathematical privacy guarantee follows the mechanism's proof and accounting.

For a new batch, prepare the attack inputs using [Data preparation, section 6](reproduction/beijing/DATA.md#6-prepare-attack-inputs).

### Resolution and privacy budget

The resolution experiment varies the public endpoint partition: K=24, 48, 96, 192, 384, and 768, with five seeds per setting. Use the [K command list](reproduction/beijing/supplement/sweeps/k_COMMANDS_CN.md).

The budget experiment uses epsilon=0.2, 0.4, 0.7, 1, 1.4, 2, and 3, with five seeds each. Use the [Budget command list](reproduction/beijing/supplement/sweeps/budget_COMMANDS_CN.md).

Each run has separate synthesis, geometry conversion, road scoring, physical-structure scoring, coordinate scoring, and road-task commands. The [endpoint diagnostic](reproduction/beijing/supplement/sweeps/endpoint_diagnostic_COMMANDS_CN.md) measures the effect of exact endpoints as a separate, non-private diagnostic.

After scoring, follow [Supplementary commands, sections 4–5](reproduction/beijing/SUPPLEMENT_COMMANDS_CN.md) to aggregate the runs and draw the main plots and the 76-metric appendix. Saved summaries are in `reference_results/k/` and `reference_results/budget/`.

### M×R matrices and figures

[Supplementary commands, section 6](reproduction/beijing/SUPPLEMENT_COMMANDS_CN.md) redraws the saved matrix from its per-cell score files using the original plotting function. It writes the full matrix, metric-group panels, comparison figures, and `cells.json`.

Use [New-batch matrix commands](reproduction/beijing/REPRODUCE_NEW_MATRIX_CN.md) for results you generate. They collect the score files and draw the same layout. Each cell keeps its source; missing values, inapplicable cases, and measured zero scores have separate representations.

## 4. Files produced by a run

```text
data/                 Downloaded data, preprocessing outputs, and public resources
plans/local_new/       Batch-specific configuration and command lists
results/local_new/     Synthetic data, routed data, scores, and plots for that batch
reference_results/    Saved experiment scores and figure inputs
setup_logs/           Environment installation logs
```

The individual command lists give the exact output path for every step. Each synthesis, routing, evaluation, and plotting command runs on its own. Keep completed outputs when moving work to another machine, then continue with the next stage.

## 5. Try a small example

The [small-example command list](reproduction/beijing/SMALL_CLI_CN.md) uses an artificial road graph and synthetic fixture inputs. It exercises the interfaces before a full run and writes its outputs under `data/cli_fixture/` and `results/cli_fixture/`.

For the regression tests, set the matcher runtime directory and run:

```powershell
$env:DFR_TEST_RUNTIME = "$PWD/data/fmm-runtime/Library/bin"
python -m pytest tests -q
```

These tests use small fixtures. The experiment command lists above generate and evaluate the dataset-scale results.
