# budget：独立的逐条实验命令

工作目录始终是交付根目录，不依赖服务器盘符。先安装README指定环境。已完成的正式实验不重跑；以下用于其他机器的新批次复现。每组生成、表示转换、评分独立执行，后一步读取前一步输出，不覆盖既有目录。

每份使用15730条全集与相同公开输出数量。种子20260719—20260723；诊断只用20260719，标记为非私有端点准确测量，不进入同预算DP比较。


## budget_0p2_seed_20260719

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p2_seed_20260719.json --length-aware
```

产物：results/portable_sweeps/budget_0p2_seed_20260719/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p2_seed_20260719/native/MTR-DFR/seed_20260719_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p2_seed_20260719/representation
```

产物：results/portable_sweeps/budget_0p2_seed_20260719/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p2_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260719/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p2_seed_20260719/road_scores
```

产物：results/portable_sweeps/budget_0p2_seed_20260719/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p2_seed_20260719/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p2_seed_20260719/physical
```

产物：results/portable_sweeps/budget_0p2_seed_20260719/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p2_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260719/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p2_seed_20260719/coordinate_scores
```

产物：results/portable_sweeps/budget_0p2_seed_20260719/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p2_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260719/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p2_seed_20260719/road_scores/manifest.json --out results/portable_sweeps/budget_0p2_seed_20260719/road_tasks
```

产物：results/portable_sweeps/budget_0p2_seed_20260719/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_0p2_seed_20260720

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p2_seed_20260720.json --length-aware
```

产物：results/portable_sweeps/budget_0p2_seed_20260720/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p2_seed_20260720/native/MTR-DFR/seed_20260720_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p2_seed_20260720/representation
```

产物：results/portable_sweeps/budget_0p2_seed_20260720/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p2_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260720/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p2_seed_20260720/road_scores
```

产物：results/portable_sweeps/budget_0p2_seed_20260720/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p2_seed_20260720/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p2_seed_20260720/physical
```

产物：results/portable_sweeps/budget_0p2_seed_20260720/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p2_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260720/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p2_seed_20260720/coordinate_scores
```

产物：results/portable_sweeps/budget_0p2_seed_20260720/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p2_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260720/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p2_seed_20260720/road_scores/manifest.json --out results/portable_sweeps/budget_0p2_seed_20260720/road_tasks
```

产物：results/portable_sweeps/budget_0p2_seed_20260720/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_0p2_seed_20260721

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p2_seed_20260721.json --length-aware
```

产物：results/portable_sweeps/budget_0p2_seed_20260721/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p2_seed_20260721/native/MTR-DFR/seed_20260721_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p2_seed_20260721/representation
```

产物：results/portable_sweeps/budget_0p2_seed_20260721/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p2_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260721/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p2_seed_20260721/road_scores
```

产物：results/portable_sweeps/budget_0p2_seed_20260721/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p2_seed_20260721/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p2_seed_20260721/physical
```

产物：results/portable_sweeps/budget_0p2_seed_20260721/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p2_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260721/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p2_seed_20260721/coordinate_scores
```

产物：results/portable_sweeps/budget_0p2_seed_20260721/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p2_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260721/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p2_seed_20260721/road_scores/manifest.json --out results/portable_sweeps/budget_0p2_seed_20260721/road_tasks
```

产物：results/portable_sweeps/budget_0p2_seed_20260721/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_0p2_seed_20260722

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p2_seed_20260722.json --length-aware
```

产物：results/portable_sweeps/budget_0p2_seed_20260722/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p2_seed_20260722/native/MTR-DFR/seed_20260722_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p2_seed_20260722/representation
```

产物：results/portable_sweeps/budget_0p2_seed_20260722/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p2_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260722/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p2_seed_20260722/road_scores
```

产物：results/portable_sweeps/budget_0p2_seed_20260722/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p2_seed_20260722/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p2_seed_20260722/physical
```

产物：results/portable_sweeps/budget_0p2_seed_20260722/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p2_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260722/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p2_seed_20260722/coordinate_scores
```

产物：results/portable_sweeps/budget_0p2_seed_20260722/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p2_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260722/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p2_seed_20260722/road_scores/manifest.json --out results/portable_sweeps/budget_0p2_seed_20260722/road_tasks
```

产物：results/portable_sweeps/budget_0p2_seed_20260722/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_0p2_seed_20260723

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p2_seed_20260723.json --length-aware
```

产物：results/portable_sweeps/budget_0p2_seed_20260723/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p2_seed_20260723/native/MTR-DFR/seed_20260723_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p2_seed_20260723/representation
```

产物：results/portable_sweeps/budget_0p2_seed_20260723/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p2_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260723/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p2_seed_20260723/road_scores
```

产物：results/portable_sweeps/budget_0p2_seed_20260723/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p2_seed_20260723/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p2_seed_20260723/physical
```

产物：results/portable_sweeps/budget_0p2_seed_20260723/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p2_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260723/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p2_seed_20260723/coordinate_scores
```

产物：results/portable_sweeps/budget_0p2_seed_20260723/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p2_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p2_seed_20260723/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p2_seed_20260723/road_scores/manifest.json --out results/portable_sweeps/budget_0p2_seed_20260723/road_tasks
```

产物：results/portable_sweeps/budget_0p2_seed_20260723/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_0p4_seed_20260719

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p4_seed_20260719.json --length-aware
```

产物：results/portable_sweeps/budget_0p4_seed_20260719/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p4_seed_20260719/native/MTR-DFR/seed_20260719_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p4_seed_20260719/representation
```

产物：results/portable_sweeps/budget_0p4_seed_20260719/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p4_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260719/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p4_seed_20260719/road_scores
```

产物：results/portable_sweeps/budget_0p4_seed_20260719/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p4_seed_20260719/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p4_seed_20260719/physical
```

产物：results/portable_sweeps/budget_0p4_seed_20260719/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p4_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260719/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p4_seed_20260719/coordinate_scores
```

产物：results/portable_sweeps/budget_0p4_seed_20260719/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p4_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260719/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p4_seed_20260719/road_scores/manifest.json --out results/portable_sweeps/budget_0p4_seed_20260719/road_tasks
```

产物：results/portable_sweeps/budget_0p4_seed_20260719/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_0p4_seed_20260720

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p4_seed_20260720.json --length-aware
```

产物：results/portable_sweeps/budget_0p4_seed_20260720/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p4_seed_20260720/native/MTR-DFR/seed_20260720_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p4_seed_20260720/representation
```

产物：results/portable_sweeps/budget_0p4_seed_20260720/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p4_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260720/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p4_seed_20260720/road_scores
```

产物：results/portable_sweeps/budget_0p4_seed_20260720/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p4_seed_20260720/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p4_seed_20260720/physical
```

产物：results/portable_sweeps/budget_0p4_seed_20260720/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p4_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260720/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p4_seed_20260720/coordinate_scores
```

产物：results/portable_sweeps/budget_0p4_seed_20260720/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p4_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260720/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p4_seed_20260720/road_scores/manifest.json --out results/portable_sweeps/budget_0p4_seed_20260720/road_tasks
```

产物：results/portable_sweeps/budget_0p4_seed_20260720/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_0p4_seed_20260721

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p4_seed_20260721.json --length-aware
```

产物：results/portable_sweeps/budget_0p4_seed_20260721/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p4_seed_20260721/native/MTR-DFR/seed_20260721_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p4_seed_20260721/representation
```

产物：results/portable_sweeps/budget_0p4_seed_20260721/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p4_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260721/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p4_seed_20260721/road_scores
```

产物：results/portable_sweeps/budget_0p4_seed_20260721/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p4_seed_20260721/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p4_seed_20260721/physical
```

产物：results/portable_sweeps/budget_0p4_seed_20260721/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p4_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260721/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p4_seed_20260721/coordinate_scores
```

产物：results/portable_sweeps/budget_0p4_seed_20260721/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p4_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260721/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p4_seed_20260721/road_scores/manifest.json --out results/portable_sweeps/budget_0p4_seed_20260721/road_tasks
```

产物：results/portable_sweeps/budget_0p4_seed_20260721/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_0p4_seed_20260722

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p4_seed_20260722.json --length-aware
```

产物：results/portable_sweeps/budget_0p4_seed_20260722/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p4_seed_20260722/native/MTR-DFR/seed_20260722_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p4_seed_20260722/representation
```

产物：results/portable_sweeps/budget_0p4_seed_20260722/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p4_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260722/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p4_seed_20260722/road_scores
```

产物：results/portable_sweeps/budget_0p4_seed_20260722/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p4_seed_20260722/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p4_seed_20260722/physical
```

产物：results/portable_sweeps/budget_0p4_seed_20260722/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p4_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260722/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p4_seed_20260722/coordinate_scores
```

产物：results/portable_sweeps/budget_0p4_seed_20260722/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p4_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260722/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p4_seed_20260722/road_scores/manifest.json --out results/portable_sweeps/budget_0p4_seed_20260722/road_tasks
```

产物：results/portable_sweeps/budget_0p4_seed_20260722/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_0p4_seed_20260723

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p4_seed_20260723.json --length-aware
```

产物：results/portable_sweeps/budget_0p4_seed_20260723/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p4_seed_20260723/native/MTR-DFR/seed_20260723_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p4_seed_20260723/representation
```

产物：results/portable_sweeps/budget_0p4_seed_20260723/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p4_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260723/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p4_seed_20260723/road_scores
```

产物：results/portable_sweeps/budget_0p4_seed_20260723/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p4_seed_20260723/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p4_seed_20260723/physical
```

产物：results/portable_sweeps/budget_0p4_seed_20260723/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p4_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260723/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p4_seed_20260723/coordinate_scores
```

产物：results/portable_sweeps/budget_0p4_seed_20260723/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p4_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p4_seed_20260723/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p4_seed_20260723/road_scores/manifest.json --out results/portable_sweeps/budget_0p4_seed_20260723/road_tasks
```

产物：results/portable_sweeps/budget_0p4_seed_20260723/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_0p7_seed_20260719

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p7_seed_20260719.json --length-aware
```

产物：results/portable_sweeps/budget_0p7_seed_20260719/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p7_seed_20260719/native/MTR-DFR/seed_20260719_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p7_seed_20260719/representation
```

产物：results/portable_sweeps/budget_0p7_seed_20260719/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p7_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260719/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p7_seed_20260719/road_scores
```

产物：results/portable_sweeps/budget_0p7_seed_20260719/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p7_seed_20260719/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p7_seed_20260719/physical
```

产物：results/portable_sweeps/budget_0p7_seed_20260719/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p7_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260719/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p7_seed_20260719/coordinate_scores
```

产物：results/portable_sweeps/budget_0p7_seed_20260719/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p7_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260719/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p7_seed_20260719/road_scores/manifest.json --out results/portable_sweeps/budget_0p7_seed_20260719/road_tasks
```

产物：results/portable_sweeps/budget_0p7_seed_20260719/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_0p7_seed_20260720

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p7_seed_20260720.json --length-aware
```

产物：results/portable_sweeps/budget_0p7_seed_20260720/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p7_seed_20260720/native/MTR-DFR/seed_20260720_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p7_seed_20260720/representation
```

产物：results/portable_sweeps/budget_0p7_seed_20260720/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p7_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260720/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p7_seed_20260720/road_scores
```

产物：results/portable_sweeps/budget_0p7_seed_20260720/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p7_seed_20260720/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p7_seed_20260720/physical
```

产物：results/portable_sweeps/budget_0p7_seed_20260720/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p7_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260720/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p7_seed_20260720/coordinate_scores
```

产物：results/portable_sweeps/budget_0p7_seed_20260720/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p7_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260720/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p7_seed_20260720/road_scores/manifest.json --out results/portable_sweeps/budget_0p7_seed_20260720/road_tasks
```

产物：results/portable_sweeps/budget_0p7_seed_20260720/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_0p7_seed_20260721

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p7_seed_20260721.json --length-aware
```

产物：results/portable_sweeps/budget_0p7_seed_20260721/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p7_seed_20260721/native/MTR-DFR/seed_20260721_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p7_seed_20260721/representation
```

产物：results/portable_sweeps/budget_0p7_seed_20260721/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p7_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260721/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p7_seed_20260721/road_scores
```

产物：results/portable_sweeps/budget_0p7_seed_20260721/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p7_seed_20260721/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p7_seed_20260721/physical
```

产物：results/portable_sweeps/budget_0p7_seed_20260721/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p7_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260721/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p7_seed_20260721/coordinate_scores
```

产物：results/portable_sweeps/budget_0p7_seed_20260721/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p7_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260721/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p7_seed_20260721/road_scores/manifest.json --out results/portable_sweeps/budget_0p7_seed_20260721/road_tasks
```

产物：results/portable_sweeps/budget_0p7_seed_20260721/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_0p7_seed_20260722

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p7_seed_20260722.json --length-aware
```

产物：results/portable_sweeps/budget_0p7_seed_20260722/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p7_seed_20260722/native/MTR-DFR/seed_20260722_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p7_seed_20260722/representation
```

产物：results/portable_sweeps/budget_0p7_seed_20260722/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p7_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260722/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p7_seed_20260722/road_scores
```

产物：results/portable_sweeps/budget_0p7_seed_20260722/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p7_seed_20260722/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p7_seed_20260722/physical
```

产物：results/portable_sweeps/budget_0p7_seed_20260722/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p7_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260722/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p7_seed_20260722/coordinate_scores
```

产物：results/portable_sweeps/budget_0p7_seed_20260722/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p7_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260722/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p7_seed_20260722/road_scores/manifest.json --out results/portable_sweeps/budget_0p7_seed_20260722/road_tasks
```

产物：results/portable_sweeps/budget_0p7_seed_20260722/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_0p7_seed_20260723

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_0p7_seed_20260723.json --length-aware
```

产物：results/portable_sweeps/budget_0p7_seed_20260723/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_0p7_seed_20260723/native/MTR-DFR/seed_20260723_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_0p7_seed_20260723/representation
```

产物：results/portable_sweeps/budget_0p7_seed_20260723/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_0p7_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260723/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_0p7_seed_20260723/road_scores
```

产物：results/portable_sweeps/budget_0p7_seed_20260723/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_0p7_seed_20260723/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_0p7_seed_20260723/physical
```

产物：results/portable_sweeps/budget_0p7_seed_20260723/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_0p7_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260723/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_0p7_seed_20260723/coordinate_scores
```

产物：results/portable_sweeps/budget_0p7_seed_20260723/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_0p7_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_0p7_seed_20260723/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_0p7_seed_20260723/road_scores/manifest.json --out results/portable_sweeps/budget_0p7_seed_20260723/road_tasks
```

产物：results/portable_sweeps/budget_0p7_seed_20260723/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_1_seed_20260719

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_1_seed_20260719.json --length-aware
```

产物：results/portable_sweeps/budget_1_seed_20260719/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_1_seed_20260719/native/MTR-DFR/seed_20260719_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_1_seed_20260719/representation
```

产物：results/portable_sweeps/budget_1_seed_20260719/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_1_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260719/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_1_seed_20260719/road_scores
```

产物：results/portable_sweeps/budget_1_seed_20260719/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_1_seed_20260719/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_1_seed_20260719/physical
```

产物：results/portable_sweeps/budget_1_seed_20260719/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_1_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260719/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_1_seed_20260719/coordinate_scores
```

产物：results/portable_sweeps/budget_1_seed_20260719/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_1_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260719/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_1_seed_20260719/road_scores/manifest.json --out results/portable_sweeps/budget_1_seed_20260719/road_tasks
```

产物：results/portable_sweeps/budget_1_seed_20260719/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_1_seed_20260720

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_1_seed_20260720.json --length-aware
```

产物：results/portable_sweeps/budget_1_seed_20260720/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_1_seed_20260720/native/MTR-DFR/seed_20260720_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_1_seed_20260720/representation
```

产物：results/portable_sweeps/budget_1_seed_20260720/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_1_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260720/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_1_seed_20260720/road_scores
```

产物：results/portable_sweeps/budget_1_seed_20260720/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_1_seed_20260720/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_1_seed_20260720/physical
```

产物：results/portable_sweeps/budget_1_seed_20260720/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_1_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260720/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_1_seed_20260720/coordinate_scores
```

产物：results/portable_sweeps/budget_1_seed_20260720/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_1_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260720/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_1_seed_20260720/road_scores/manifest.json --out results/portable_sweeps/budget_1_seed_20260720/road_tasks
```

产物：results/portable_sweeps/budget_1_seed_20260720/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_1_seed_20260721

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_1_seed_20260721.json --length-aware
```

产物：results/portable_sweeps/budget_1_seed_20260721/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_1_seed_20260721/native/MTR-DFR/seed_20260721_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_1_seed_20260721/representation
```

产物：results/portable_sweeps/budget_1_seed_20260721/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_1_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260721/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_1_seed_20260721/road_scores
```

产物：results/portable_sweeps/budget_1_seed_20260721/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_1_seed_20260721/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_1_seed_20260721/physical
```

产物：results/portable_sweeps/budget_1_seed_20260721/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_1_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260721/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_1_seed_20260721/coordinate_scores
```

产物：results/portable_sweeps/budget_1_seed_20260721/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_1_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260721/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_1_seed_20260721/road_scores/manifest.json --out results/portable_sweeps/budget_1_seed_20260721/road_tasks
```

产物：results/portable_sweeps/budget_1_seed_20260721/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_1_seed_20260722

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_1_seed_20260722.json --length-aware
```

产物：results/portable_sweeps/budget_1_seed_20260722/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_1_seed_20260722/native/MTR-DFR/seed_20260722_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_1_seed_20260722/representation
```

产物：results/portable_sweeps/budget_1_seed_20260722/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_1_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260722/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_1_seed_20260722/road_scores
```

产物：results/portable_sweeps/budget_1_seed_20260722/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_1_seed_20260722/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_1_seed_20260722/physical
```

产物：results/portable_sweeps/budget_1_seed_20260722/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_1_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260722/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_1_seed_20260722/coordinate_scores
```

产物：results/portable_sweeps/budget_1_seed_20260722/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_1_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260722/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_1_seed_20260722/road_scores/manifest.json --out results/portable_sweeps/budget_1_seed_20260722/road_tasks
```

产物：results/portable_sweeps/budget_1_seed_20260722/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_1_seed_20260723

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_1_seed_20260723.json --length-aware
```

产物：results/portable_sweeps/budget_1_seed_20260723/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_1_seed_20260723/native/MTR-DFR/seed_20260723_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_1_seed_20260723/representation
```

产物：results/portable_sweeps/budget_1_seed_20260723/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_1_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260723/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_1_seed_20260723/road_scores
```

产物：results/portable_sweeps/budget_1_seed_20260723/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_1_seed_20260723/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_1_seed_20260723/physical
```

产物：results/portable_sweeps/budget_1_seed_20260723/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_1_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260723/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_1_seed_20260723/coordinate_scores
```

产物：results/portable_sweeps/budget_1_seed_20260723/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_1_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1_seed_20260723/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_1_seed_20260723/road_scores/manifest.json --out results/portable_sweeps/budget_1_seed_20260723/road_tasks
```

产物：results/portable_sweeps/budget_1_seed_20260723/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_1p4_seed_20260719

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_1p4_seed_20260719.json --length-aware
```

产物：results/portable_sweeps/budget_1p4_seed_20260719/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_1p4_seed_20260719/native/MTR-DFR/seed_20260719_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_1p4_seed_20260719/representation
```

产物：results/portable_sweeps/budget_1p4_seed_20260719/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_1p4_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260719/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_1p4_seed_20260719/road_scores
```

产物：results/portable_sweeps/budget_1p4_seed_20260719/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_1p4_seed_20260719/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_1p4_seed_20260719/physical
```

产物：results/portable_sweeps/budget_1p4_seed_20260719/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_1p4_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260719/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_1p4_seed_20260719/coordinate_scores
```

产物：results/portable_sweeps/budget_1p4_seed_20260719/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_1p4_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260719/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_1p4_seed_20260719/road_scores/manifest.json --out results/portable_sweeps/budget_1p4_seed_20260719/road_tasks
```

产物：results/portable_sweeps/budget_1p4_seed_20260719/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_1p4_seed_20260720

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_1p4_seed_20260720.json --length-aware
```

产物：results/portable_sweeps/budget_1p4_seed_20260720/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_1p4_seed_20260720/native/MTR-DFR/seed_20260720_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_1p4_seed_20260720/representation
```

产物：results/portable_sweeps/budget_1p4_seed_20260720/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_1p4_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260720/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_1p4_seed_20260720/road_scores
```

产物：results/portable_sweeps/budget_1p4_seed_20260720/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_1p4_seed_20260720/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_1p4_seed_20260720/physical
```

产物：results/portable_sweeps/budget_1p4_seed_20260720/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_1p4_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260720/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_1p4_seed_20260720/coordinate_scores
```

产物：results/portable_sweeps/budget_1p4_seed_20260720/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_1p4_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260720/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_1p4_seed_20260720/road_scores/manifest.json --out results/portable_sweeps/budget_1p4_seed_20260720/road_tasks
```

产物：results/portable_sweeps/budget_1p4_seed_20260720/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_1p4_seed_20260721

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_1p4_seed_20260721.json --length-aware
```

产物：results/portable_sweeps/budget_1p4_seed_20260721/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_1p4_seed_20260721/native/MTR-DFR/seed_20260721_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_1p4_seed_20260721/representation
```

产物：results/portable_sweeps/budget_1p4_seed_20260721/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_1p4_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260721/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_1p4_seed_20260721/road_scores
```

产物：results/portable_sweeps/budget_1p4_seed_20260721/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_1p4_seed_20260721/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_1p4_seed_20260721/physical
```

产物：results/portable_sweeps/budget_1p4_seed_20260721/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_1p4_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260721/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_1p4_seed_20260721/coordinate_scores
```

产物：results/portable_sweeps/budget_1p4_seed_20260721/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_1p4_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260721/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_1p4_seed_20260721/road_scores/manifest.json --out results/portable_sweeps/budget_1p4_seed_20260721/road_tasks
```

产物：results/portable_sweeps/budget_1p4_seed_20260721/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_1p4_seed_20260722

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_1p4_seed_20260722.json --length-aware
```

产物：results/portable_sweeps/budget_1p4_seed_20260722/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_1p4_seed_20260722/native/MTR-DFR/seed_20260722_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_1p4_seed_20260722/representation
```

产物：results/portable_sweeps/budget_1p4_seed_20260722/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_1p4_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260722/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_1p4_seed_20260722/road_scores
```

产物：results/portable_sweeps/budget_1p4_seed_20260722/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_1p4_seed_20260722/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_1p4_seed_20260722/physical
```

产物：results/portable_sweeps/budget_1p4_seed_20260722/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_1p4_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260722/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_1p4_seed_20260722/coordinate_scores
```

产物：results/portable_sweeps/budget_1p4_seed_20260722/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_1p4_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260722/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_1p4_seed_20260722/road_scores/manifest.json --out results/portable_sweeps/budget_1p4_seed_20260722/road_tasks
```

产物：results/portable_sweeps/budget_1p4_seed_20260722/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_1p4_seed_20260723

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_1p4_seed_20260723.json --length-aware
```

产物：results/portable_sweeps/budget_1p4_seed_20260723/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_1p4_seed_20260723/native/MTR-DFR/seed_20260723_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_1p4_seed_20260723/representation
```

产物：results/portable_sweeps/budget_1p4_seed_20260723/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_1p4_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260723/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_1p4_seed_20260723/road_scores
```

产物：results/portable_sweeps/budget_1p4_seed_20260723/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_1p4_seed_20260723/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_1p4_seed_20260723/physical
```

产物：results/portable_sweeps/budget_1p4_seed_20260723/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_1p4_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260723/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_1p4_seed_20260723/coordinate_scores
```

产物：results/portable_sweeps/budget_1p4_seed_20260723/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_1p4_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_1p4_seed_20260723/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_1p4_seed_20260723/road_scores/manifest.json --out results/portable_sweeps/budget_1p4_seed_20260723/road_tasks
```

产物：results/portable_sweeps/budget_1p4_seed_20260723/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_2_seed_20260719

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_2_seed_20260719.json --length-aware
```

产物：results/portable_sweeps/budget_2_seed_20260719/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_2_seed_20260719/native/MTR-DFR/seed_20260719_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_2_seed_20260719/representation
```

产物：results/portable_sweeps/budget_2_seed_20260719/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_2_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260719/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_2_seed_20260719/road_scores
```

产物：results/portable_sweeps/budget_2_seed_20260719/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_2_seed_20260719/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_2_seed_20260719/physical
```

产物：results/portable_sweeps/budget_2_seed_20260719/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_2_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260719/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_2_seed_20260719/coordinate_scores
```

产物：results/portable_sweeps/budget_2_seed_20260719/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_2_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260719/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_2_seed_20260719/road_scores/manifest.json --out results/portable_sweeps/budget_2_seed_20260719/road_tasks
```

产物：results/portable_sweeps/budget_2_seed_20260719/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_2_seed_20260720

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_2_seed_20260720.json --length-aware
```

产物：results/portable_sweeps/budget_2_seed_20260720/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_2_seed_20260720/native/MTR-DFR/seed_20260720_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_2_seed_20260720/representation
```

产物：results/portable_sweeps/budget_2_seed_20260720/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_2_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260720/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_2_seed_20260720/road_scores
```

产物：results/portable_sweeps/budget_2_seed_20260720/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_2_seed_20260720/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_2_seed_20260720/physical
```

产物：results/portable_sweeps/budget_2_seed_20260720/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_2_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260720/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_2_seed_20260720/coordinate_scores
```

产物：results/portable_sweeps/budget_2_seed_20260720/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_2_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260720/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_2_seed_20260720/road_scores/manifest.json --out results/portable_sweeps/budget_2_seed_20260720/road_tasks
```

产物：results/portable_sweeps/budget_2_seed_20260720/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_2_seed_20260721

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_2_seed_20260721.json --length-aware
```

产物：results/portable_sweeps/budget_2_seed_20260721/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_2_seed_20260721/native/MTR-DFR/seed_20260721_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_2_seed_20260721/representation
```

产物：results/portable_sweeps/budget_2_seed_20260721/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_2_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260721/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_2_seed_20260721/road_scores
```

产物：results/portable_sweeps/budget_2_seed_20260721/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_2_seed_20260721/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_2_seed_20260721/physical
```

产物：results/portable_sweeps/budget_2_seed_20260721/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_2_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260721/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_2_seed_20260721/coordinate_scores
```

产物：results/portable_sweeps/budget_2_seed_20260721/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_2_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260721/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_2_seed_20260721/road_scores/manifest.json --out results/portable_sweeps/budget_2_seed_20260721/road_tasks
```

产物：results/portable_sweeps/budget_2_seed_20260721/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_2_seed_20260722

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_2_seed_20260722.json --length-aware
```

产物：results/portable_sweeps/budget_2_seed_20260722/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_2_seed_20260722/native/MTR-DFR/seed_20260722_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_2_seed_20260722/representation
```

产物：results/portable_sweeps/budget_2_seed_20260722/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_2_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260722/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_2_seed_20260722/road_scores
```

产物：results/portable_sweeps/budget_2_seed_20260722/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_2_seed_20260722/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_2_seed_20260722/physical
```

产物：results/portable_sweeps/budget_2_seed_20260722/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_2_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260722/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_2_seed_20260722/coordinate_scores
```

产物：results/portable_sweeps/budget_2_seed_20260722/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_2_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260722/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_2_seed_20260722/road_scores/manifest.json --out results/portable_sweeps/budget_2_seed_20260722/road_tasks
```

产物：results/portable_sweeps/budget_2_seed_20260722/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_2_seed_20260723

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_2_seed_20260723.json --length-aware
```

产物：results/portable_sweeps/budget_2_seed_20260723/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_2_seed_20260723/native/MTR-DFR/seed_20260723_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_2_seed_20260723/representation
```

产物：results/portable_sweeps/budget_2_seed_20260723/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_2_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260723/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_2_seed_20260723/road_scores
```

产物：results/portable_sweeps/budget_2_seed_20260723/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_2_seed_20260723/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_2_seed_20260723/physical
```

产物：results/portable_sweeps/budget_2_seed_20260723/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_2_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260723/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_2_seed_20260723/coordinate_scores
```

产物：results/portable_sweeps/budget_2_seed_20260723/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_2_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_2_seed_20260723/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_2_seed_20260723/road_scores/manifest.json --out results/portable_sweeps/budget_2_seed_20260723/road_tasks
```

产物：results/portable_sweeps/budget_2_seed_20260723/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_3_seed_20260719

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_3_seed_20260719.json --length-aware
```

产物：results/portable_sweeps/budget_3_seed_20260719/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_3_seed_20260719/native/MTR-DFR/seed_20260719_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_3_seed_20260719/representation
```

产物：results/portable_sweeps/budget_3_seed_20260719/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_3_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260719/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_3_seed_20260719/road_scores
```

产物：results/portable_sweeps/budget_3_seed_20260719/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_3_seed_20260719/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_3_seed_20260719/physical
```

产物：results/portable_sweeps/budget_3_seed_20260719/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_3_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260719/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_3_seed_20260719/coordinate_scores
```

产物：results/portable_sweeps/budget_3_seed_20260719/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_3_seed_20260719.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260719/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_3_seed_20260719/road_scores/manifest.json --out results/portable_sweeps/budget_3_seed_20260719/road_tasks
```

产物：results/portable_sweeps/budget_3_seed_20260719/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_3_seed_20260720

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_3_seed_20260720.json --length-aware
```

产物：results/portable_sweeps/budget_3_seed_20260720/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_3_seed_20260720/native/MTR-DFR/seed_20260720_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_3_seed_20260720/representation
```

产物：results/portable_sweeps/budget_3_seed_20260720/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_3_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260720/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_3_seed_20260720/road_scores
```

产物：results/portable_sweeps/budget_3_seed_20260720/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_3_seed_20260720/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_3_seed_20260720/physical
```

产物：results/portable_sweeps/budget_3_seed_20260720/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_3_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260720/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_3_seed_20260720/coordinate_scores
```

产物：results/portable_sweeps/budget_3_seed_20260720/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_3_seed_20260720.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260720/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_3_seed_20260720/road_scores/manifest.json --out results/portable_sweeps/budget_3_seed_20260720/road_tasks
```

产物：results/portable_sweeps/budget_3_seed_20260720/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_3_seed_20260721

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_3_seed_20260721.json --length-aware
```

产物：results/portable_sweeps/budget_3_seed_20260721/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_3_seed_20260721/native/MTR-DFR/seed_20260721_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_3_seed_20260721/representation
```

产物：results/portable_sweeps/budget_3_seed_20260721/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_3_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260721/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_3_seed_20260721/road_scores
```

产物：results/portable_sweeps/budget_3_seed_20260721/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_3_seed_20260721/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_3_seed_20260721/physical
```

产物：results/portable_sweeps/budget_3_seed_20260721/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_3_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260721/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_3_seed_20260721/coordinate_scores
```

产物：results/portable_sweeps/budget_3_seed_20260721/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_3_seed_20260721.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260721/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_3_seed_20260721/road_scores/manifest.json --out results/portable_sweeps/budget_3_seed_20260721/road_tasks
```

产物：results/portable_sweeps/budget_3_seed_20260721/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_3_seed_20260722

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_3_seed_20260722.json --length-aware
```

产物：results/portable_sweeps/budget_3_seed_20260722/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_3_seed_20260722/native/MTR-DFR/seed_20260722_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_3_seed_20260722/representation
```

产物：results/portable_sweeps/budget_3_seed_20260722/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_3_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260722/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_3_seed_20260722/road_scores
```

产物：results/portable_sweeps/budget_3_seed_20260722/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_3_seed_20260722/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_3_seed_20260722/physical
```

产物：results/portable_sweeps/budget_3_seed_20260722/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_3_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260722/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_3_seed_20260722/coordinate_scores
```

产物：results/portable_sweeps/budget_3_seed_20260722/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_3_seed_20260722.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260722/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_3_seed_20260722/road_scores/manifest.json --out results/portable_sweeps/budget_3_seed_20260722/road_tasks
```

产物：results/portable_sweeps/budget_3_seed_20260722/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。


## budget_3_seed_20260723

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config supplement/sweeps/budget_3_seed_20260723.json --length-aware
```

产物：results/portable_sweeps/budget_3_seed_20260723/native/MTR-DFR；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/portable_sweeps/budget_3_seed_20260723/native/MTR-DFR/seed_20260723_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 15730 --out results/portable_sweeps/budget_3_seed_20260723/representation
```

产物：results/portable_sweeps/budget_3_seed_20260723/representation；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate.py --config supplement/sweeps/budget_3_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260723/representation/synthetic_routes.pkl.gz --out results/portable_sweeps/budget_3_seed_20260723/road_scores
```

产物：results/portable_sweeps/budget_3_seed_20260723/road_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe legacy/evaluation/run_physical_experiment.py --real-routes resources/dataset/road_records.pkl.gz --synthetic-routes results/portable_sweeps/budget_3_seed_20260723/representation/synthetic_routes.pkl.gz --edge-cache resources/metric_cache/metric_cache.pkl.gz --network resources/network/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/portable_sweeps/budget_3_seed_20260723/physical
```

产物：results/portable_sweeps/budget_3_seed_20260723/physical；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config supplement/sweeps/budget_3_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260723/representation/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/portable_sweeps/budget_3_seed_20260723/coordinate_scores
```

产物：results/portable_sweeps/budget_3_seed_20260723/coordinate_scores；失败时保留该步骤日志与部分产物，不继续评分。

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config supplement/sweeps/budget_3_seed_20260723.json --method MTR-DFR --router Origin --input results/portable_sweeps/budget_3_seed_20260723/representation/synthetic_routes.pkl.gz --score-manifest results/portable_sweeps/budget_3_seed_20260723/road_scores/manifest.json --out results/portable_sweeps/budget_3_seed_20260723/road_tasks
```

产物：results/portable_sweeps/budget_3_seed_20260723/road_tasks；失败时保留该步骤日志与部分产物，不继续评分。

