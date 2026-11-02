# endpoint_diagnostic：独立的逐条实验命令

按仓库根 README 第8步准备配置，并在同一 PowerShell 窗口执行本页。本页随仓库提供，不由运行命令生成。`configs/experiments/` 是当前数据的配置目录；`results/` 下的名称以北京复现为例，不是必须的文件名。更改结果目录时，将本页及依赖文档中对应的 `--out`、`--input`、`--source` 等路径同步替换；不要改算法名、预算或种子来代替改文件名。Porto 使用另一个检出目录，命令相同。

工作目录始终是交付根目录，不依赖服务器盘符。先安装README指定环境。已完成的正式实验不重跑；以下用于其他机器的新批次复现。每组生成、表示转换、评分独立执行，后一步读取前一步输出，不覆盖既有目录。

每份使用15730条全集与相同公开输出数量。种子20260719—20260723；诊断只用20260719，标记为非私有端点准确测量，不进入同预算DP比较。


## endpoint_diagnostic_96_seed_20260719

```powershell
.venv/Scripts/python.exe supplement/k_original/synthesize_endpoint_diagnostic.py --config configs/experiments/supplement/sweeps/endpoint_diagnostic_96_seed_20260719.json --length-aware --endpoint-partition resources/endpoint_partitions/partition96.json
```

产物：results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/native/MTR-DFR/seed_20260719_length/road_routes.pkl.gz --source-cache "$MetricCache" --network "$Network" --expected-slots $FullSlots --out results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/representation
```

产物：results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config configs/experiments/supplement/sweeps/endpoint_diagnostic_96_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/road_scores
```

产物：results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes "$RoadRecords" --synthetic-routes results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/representation/synthetic_routes.pkl.gz --edge-cache "$MetricCache" --network "$Network" --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/physical
```

产物：results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config configs/experiments/supplement/sweeps/endpoint_diagnostic_96_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/coordinate_scores
```

产物：results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config configs/experiments/supplement/sweeps/endpoint_diagnostic_96_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/road_scores/manifest.json --out results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/road_tasks
```

产物：results/portable_sweeps/endpoint_diagnostic_96_seed_20260719/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## endpoint_diagnostic_384_seed_20260719

```powershell
.venv/Scripts/python.exe supplement/k_original/synthesize_endpoint_diagnostic.py --config configs/experiments/supplement/sweeps/endpoint_diagnostic_384_seed_20260719.json --length-aware --endpoint-partition resources/endpoint_partitions/partition384.json
```

产物：results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/native/MTR-DFR/seed_20260719_length/road_routes.pkl.gz --source-cache "$MetricCache" --network "$Network" --expected-slots $FullSlots --out results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/representation
```

产物：results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config configs/experiments/supplement/sweeps/endpoint_diagnostic_384_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/road_scores
```

产物：results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes "$RoadRecords" --synthetic-routes results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/representation/synthetic_routes.pkl.gz --edge-cache "$MetricCache" --network "$Network" --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/physical
```

产物：results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config configs/experiments/supplement/sweeps/endpoint_diagnostic_384_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/coordinate_scores
```

产物：results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config configs/experiments/supplement/sweeps/endpoint_diagnostic_384_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/road_scores/manifest.json --out results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/road_tasks
```

产物：results/portable_sweeps/endpoint_diagnostic_384_seed_20260719/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## endpoint_diagnostic_768_seed_20260719

```powershell
.venv/Scripts/python.exe supplement/k_original/synthesize_endpoint_diagnostic.py --config configs/experiments/supplement/sweeps/endpoint_diagnostic_768_seed_20260719.json --length-aware --endpoint-partition resources/endpoint_partitions/partition768.json
```

产物：results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/native/MTR-DFR/seed_20260719_length/road_routes.pkl.gz --source-cache "$MetricCache" --network "$Network" --expected-slots $FullSlots --out results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/representation
```

产物：results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config configs/experiments/supplement/sweeps/endpoint_diagnostic_768_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/road_scores
```

产物：results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes "$RoadRecords" --synthetic-routes results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/representation/synthetic_routes.pkl.gz --edge-cache "$MetricCache" --network "$Network" --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/physical
```

产物：results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config configs/experiments/supplement/sweeps/endpoint_diagnostic_768_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/coordinate_scores
```

产物：results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config configs/experiments/supplement/sweeps/endpoint_diagnostic_768_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/road_scores/manifest.json --out results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/road_tasks
```

产物：results/portable_sweeps/endpoint_diagnostic_768_seed_20260719/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。

