# MTR-DFR

MTR-DFR generates synthetic road trajectories from differentially private measurements. This repository includes the algorithm, baseline implementations, evaluation tools, saved synthetic datasets, and plotting code.

[中文说明](README_CN.md) · [Step-by-step experiment guide](reproduction/beijing/README.md) · [Data download and preprocessing](reproduction/beijing/DATA.md)

## Start here

The current Beijing workflow is in [`reproduction/beijing`](reproduction/beijing). It separates data preparation, synthesis, routing, evaluation, and plotting. Follow its [English guide](reproduction/beijing/README.md) in order to run the experiments on your own machine.

Install [Git LFS](https://git-lfs.com/) before downloading the datasets and public road resources:

```powershell
git lfs install
git clone https://github.com/Science-openmycode/DFR.git
cd DFR
git lfs pull
cd reproduction/beijing
```

The supplied FMM and STMatch executables run on Windows x64. Use Python 3.13.9 and the pinned dependencies described in the guide. MTNet training also requires an NVIDIA GPU.

## Run the experiments

1. [Install the environment](reproduction/beijing/README.md#1-install-the-environment).
2. [Download GeoLife and prepare the road dataset](reproduction/beijing/DATA.md). The preprocessing program reads the original GPS files, restores timestamps, and matches trajectories to the supplied public road graph.
3. Generate synthetic data. Run SPRT, PrivTrace, DPTraj-PM, and DPStd as measurement methods, or use MTR-DFR, DPMM, and MTNet as native road generators.
4. Route each statistical method's output with Origin, Nearest, FMM, STMatch, or MM2-MDP. Each router reads the synthetic output and the public graph.
5. Evaluate distribution fidelity, road coverage, route choice, and downstream tasks. Run the component ablations and the resolution and privacy-budget sweeps.
6. Plot the results. Plotting reads the score files produced by evaluation; synthesis and routing are separate commands.

The [experiment guide](reproduction/beijing/README.md#3-experiment-order) links the command lists for each stage and explains their outputs. For a new dataset batch, the preprocessing workflow creates command lists with your input paths and output directories.

## Data and results

Download the original GeoLife trajectories from Microsoft using the [data guide](reproduction/beijing/DATA.md). The repository supplies the public Beijing road graph through Git LFS.

The current road-level Beijing reference contains 15,730 trajectories. Full-corpus experiments compare a synthetic dataset of the same size with this reference. Strict TSTR uses a separate 12,584/3,146 train/test split: fit the synthesizer on the real training set, train the downstream predictor on synthetic training data, and evaluate on the real test set.

Earlier coordinate-level experiments use 17,123 trajectories. Their saved data and figures remain in the root-level `datasets/` and `experiment_results/` directories. The current road-level guide uses its own batch configurations and results.

## Directory guide

```text
reproduction/beijing/
  preprocess/        Download and prepare the input data
  algorithms/        Measurement methods, routers, and native generators
  configs/           Dataset paths and experiment parameters
  evaluation/        Metric implementations
  experiments/       Evaluation and plotting entry points
  supplement/        Resolution and privacy-budget experiment configurations
  reference_results/ Saved scores and figure inputs
  results/           Outputs from your runs
datasets/synthetic/  Earlier saved synthetic datasets
experiment_results/  Earlier saved evaluation results and figures
```

See the license and citation information alongside each external dataset, road resource, and baseline implementation.
