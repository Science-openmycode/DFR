# Data download and preprocessing

[Experiment guide](../../README.md) · [中文说明](DATA_CN.md)

Run these commands from `reproduction/beijing` after installing the environment in the experiment guide. Activate `.venv` so that `python` uses its interpreter.

## 1. Download GeoLife

Get the original trajectories from the [Microsoft GeoLife download page](https://www.microsoft.com/en-us/download/details.aspx?id=52367), or use the downloader:

```powershell
python preprocess/fetch_geolife.py --archive data/downloads/geolife_1.3.zip --extract-to data/geolife
```

`--archive` specifies where to save the ZIP; it also accepts a ZIP you downloaded yourself. `--extract-to` must be a new directory. The program checks archive integrity and extracts the files to `data/geolife/Geolife Trajectories 1.3/Data/<user>/Trajectory/*.plt`.

The archive is named *Geolife Trajectories 1.3.zip*; the download page lists version 1.2.2. Keep the dataset documentation and follow Microsoft's data-use and citation terms. The archive contains 18,670 PLT files before filtering.

## 2. Parse coordinates and recover timestamps

```powershell
python legacy/commands/prepare_geolife_beijing.py --source-dir "data/geolife/Geolife Trajectories 1.3/Data" --out data/raw/real_full_frozen.pkl --seed 20260713 --train-fraction 0.8 --bbox 39.75 40.15 116.10 116.65
python preprocess/recover_raw_metadata.py --source-dir "data/geolife/Geolife Trajectories 1.3/Data" --coordinates data/raw/real_full_frozen.pkl --out data/raw/metadata
python preprocess/prepare_mtnet_time_binding.py --source-dir "data/geolife/Geolife Trajectories 1.3/Data" --reference data/raw/real_full_frozen.pkl --out data/raw/mtnet_time_binding.json
```

The first command reads PLT files in sorted path order, skips their six-line headers, keeps points within the Beijing bounding box, and retains trajectories with at least two points. `--bbox` gives minimum latitude, maximum latitude, minimum longitude, and maximum longitude. The seed controls the trajectory order; `--train-fraction` sets the coordinate-level training split. The supplied GeoLife input gives 17,123 coordinate trajectories.

The second command associates the retained points with their original timestamps. It writes `timestamps_day_serial.pkl.gz`, `original_observation_indices.pkl.gz`, `source_binding.csv`, and `report.json`. Timestamp differences are in days; multiply by 86,400 for seconds. Use a new output directory.

The third command prepares the start/end time information needed by MTNet, using the same file order and trajectory permutation. It writes `mtnet_time_binding.json`. Keep these real-data preprocessing files in `data/`; synthesis writes separate datasets under `results/`.

## 3. Install the public road graph

The repository includes [beijing_full_20261026.zip](../../public_assets/beijing_full_20261026.zip) through Git LFS. Its source and OSM license are in [BEIJING_FULL_LICENSE.md](../../public_assets/BEIJING_FULL_LICENSE.md).

```powershell
python preprocess/install_public_roads.py --out data/public
```

This creates `data/public/network/network.shp`, its companion files, and `data/public/osm/osm_cache_beijing_drivable_full.pkl`. `--out` must be a new directory. Use `--archive` to select another location for this same archive. The supplied graph fixes the road identifiers and geometry used by the experiment.

## 4. Prepare the road-matching runtime

The Windows FMM/STMatch executables are in `resources/fmm/` and `resources/stmatch/`. Their upstream source is [FMM](https://github.com/cyang-kth/fmm). Install their dependencies with Conda, then set the environment variables in the terminal where you run matching:

```powershell
conda create --prefix ./data/fmm-runtime --override-channels --channel conda-forge --repodata-fn repodata.json libgdal=2.4.4 boost-cpp=1.75.0 conda-launchers --yes
$env:PATH = "$PWD/data/fmm-runtime/Library/bin;$env:PATH"
$env:GDAL_DATA = "$PWD/data/fmm-runtime/Library/share/gdal"
$env:PROJ_LIB = "$PWD/data/fmm-runtime/Library/share/proj"
```

Review the preprocessing configuration, then run matching:

```powershell
python prepare_roads.py --config configs/preprocess_beijing_8_16.json --out data/road_review --dry-run
python prepare_roads.py --config configs/preprocess_beijing_8_16.json --out data/road_review --review-only
```

`--dry-run` prints the configured inputs and matching parameters. The next command performs the matching. The configuration uses all points, 8 then 16 candidates, a 200 m search radius, a 50 m GPS error parameter, and eight threads. Change `threads` for your machine while retaining the matching parameters.

The run writes chunk-level evidence, `reviewed_records.pkl.gz`, `selection.csv`, and `selection_review.json`. If the program requests a review of the selected road subset, it exits with code 2. Read the selection report, then accept that subset in a new output directory:

```powershell
python prepare_roads.py --config configs/preprocess_beijing_8_16.json --out data/road_accepted --review-from data/road_review --accept-reviewed-subset yes
```

The accepted dataset is written to `data/road_accepted/dataset`. The review-only command does not create a final corpus. Acceptance reuses its records without importing or invoking the matcher. The historical road batch contains 15,730 trajectories, split into 12,584 training and 3,146 test trajectories. Your run reports its own retained count and selection reasons.

The parameter preview takes a few seconds; allow several hours for full matching. One earlier four-thread run processed 15,488 trajectories in about five hours. A separate eight-thread retry of 515 difficult trajectories took about two hours. The third step should take minutes to tens of minutes, mostly for reading data and projecting coordinates. With a complete `dataset` directory, skip to `bind_dataset.py --dataset` below. To rescore or redraw figures, use the saved synthetic datasets in `datasets/synthetic/` and results in `reference_results/`.

## 5. Create a new experiment batch

Download MM2 version 1.2.1, bind the prepared data and public resources, prepare the split and routing table, then generate the batch's command lists:

```powershell
python preprocess/fetch_mm2.py --archive data/downloads/mm2_1.2.1.zip --extract-to data/mm2_upstream --install-to resources/mm2/map_matching_2.exe
python bind_dataset.py --dataset data/road_accepted/dataset --osm-cache data/public/osm/osm_cache_beijing_drivable_full.pkl --runtime data/fmm-runtime/Library/bin --mm2 resources/mm2/map_matching_2.exe --mm2-network resources/mm2/network --out configs/local_new.json --batch local_new
python prepare_public_resources.py --config configs/local_new.json --frozen-support resources --out-config configs/local_public.json
python prepare_tstr_split.py --config configs/local_public.json --out data/local_split --out-config configs/local_split.json
python prepare_ubodt.py --config configs/local_split.json --out-dir data/local_ubodt --out-config configs/local_ready.json --delta-m 1500 --threads 4
python tools/write_batch_commands.py --config configs/local_ready.json --time-binding data/raw/mtnet_time_binding.json --raw-reference data/raw/real_full_frozen.pkl --out plans/local_new
```

- `--dataset` selects the accepted road dataset. `--batch` names this run's output namespace.
- `--runtime` selects the FMM runtime directory. When moving to another machine, use `--network data/public/network/network.shp` with `bind_dataset.py` to bind the graph's new location.
- `--frozen-support` selects the supplied public graph caches. The preparation command constructs the public resources for the batch.
- `prepare_tstr_split.py` uses the dataset's existing train/test split.
- UBODT uses a 1,500 m distance threshold and needs about 6 GB of disk space. `--threads` controls its parallelism.
- The final command writes configuration and command documents to `plans/local_new/`; run the generated commands in order to perform synthesis, routing, scoring, TSTR, and sensitivity experiments. Their outputs go to `results/local_new/`.

Each output configuration or preparation directory must be new. Use another batch name and output directory for a separate run.

## 6. Prepare attack inputs

After generating and registering the training-only synthetic releases, create `configs/local_attack_releases.json`. Add each method's synthetic coordinate file and its registered lineage file:

```json
{
  "MTR-DFR": {
    "coordinates": "results/local_new/<training-release>/coordinates.pkl",
    "lineage": "results/local_new/<training-release>/lineage.json"
  }
}
```

Replace `<training-release>` with the output directory from that method's training-only commands. Then run:

```powershell
python prepare_attack_inputs.py --config configs/local_ready.json --releases configs/local_attack_releases.json --out data/local_attack --out-config configs/local_attack.json
python experiments/privacy_attack.py --config configs/local_attack.json --batch local_attack
python experiments/plot.py --config configs/local_attack.json --experiment privacy_attack --batch local_attack
```

The first command prepares member, nonmember, and reference sets using seed 20260715. It samples up to 1,000 members from the real training split and 1,000 nonmembers from the real test split, and uses the remaining test records as reference. The next commands score the releases and draw the attack results. Keep the real-data attack inputs separate from synthetic releases.
