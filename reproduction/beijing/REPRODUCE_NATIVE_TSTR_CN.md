# 新生成原生结果 → 严格 TSTR

先按DFR生成说明或原生基线说明完成训练专用发布。以下读取新批次，不读取保存的旧分数，不重新训练生成器。所有路径相对本目录；输出已存在时停止，保留旧结果。每个评分命令在合成训练集训练任务模型，在同一3146条真实测试集测试。

## 1. DPMM

上一节DPMM的start、生成、finish三个命令完成后，验证实际退出记录、12584条训练输入和已验证加速器，恢复缺失输出槽位为空，不填造轨迹：

```powershell
.venv/Scripts/python.exe tools/prepare_dpmm_train_evaluation.py --directory results/reproduction_native_20261024/train/DPMM --config configs/beijing.json --ledger results/reproduction_native_20261024/train/dpmm_execution.jsonl --document REPRODUCE_NATIVE_BASELINES_20261024_CN.md --validation vendor/dpmm/evidence/train_accelerated.json --out results/reproduction_native_20261024/train/DPMM_view
```

输出coordinates.pkl、manifest.json、lineage.json。随后评分：

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/beijing.json --method DPMM --input results/reproduction_native_20261024/train/DPMM_view/coordinates.pkl --lineage results/reproduction_native_20261024/train/DPMM_view/lineage.json --metric-protocol audit-v2 --out results/reproduction_native_20261024/tstr_audit_v2/DPMM/Origin
```

## 2. MTNet

RUN_MTNET_GPU.ps1已保存训练和生成子进程退出码；以下同时检查30轮训练日志、训练划分、模型和原生发布：

```powershell
.venv/Scripts/python.exe tools/finalize_mtnet_lineage.py --directory results/reproduction_native_20261024/train/MTNet_deployment --preparation results/reproduction_native_20261024/train/MTNet_prepared/full_preparation_manifest.json --config configs/beijing.json
```

输出部署目录内lineage.json。再登记原生道路ID，不做匹配：

```powershell
.venv/Scripts/python.exe register_mtnet.py --config configs/beijing.json --source results/reproduction_native_20261024/train/MTNet_deployment/native_release --train-only --preparation results/reproduction_native_20261024/train/MTNet_prepared/full_preparation_manifest.json --model results/reproduction_native_20261024/train/MTNet_deployment/trained/model.pt --out results/reproduction_native_20261024/train/MTNet_routes
```

转换公共边的确定几何，保留槽位和原生来源绑定：

```powershell
.venv/Scripts/python.exe tools/stage_native_saved_coordinates.py --routes results/reproduction_native_20261024/train/MTNet_routes/synthetic_routes.pkl.gz --network resources/network/network.shp --edge-cache resources/edge_cache/edge_cache.pkl.gz --native-source results/reproduction_native_20261024/train/MTNet_deployment/native_release/routes.pkl --for-tstr --out-dir results/reproduction_native_20261024/train/MTNet_view
```

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/beijing.json --method MTNet --input results/reproduction_native_20261024/train/MTNet_view/coordinates.pkl --lineage results/reproduction_native_20261024/train/MTNet_deployment/lineage.json --metric-protocol audit-v2 --out results/reproduction_native_20261024/tstr_audit_v2/MTNet/Origin
```

## 3. MTR-DFR

原生节点对只转换为同一公共边的ID，不重新路由：

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/reproduction_dfr_length_20261024/native_train/MTR-DFR/release/seed_42_length/road_routes.pkl.gz --network resources/network/network.shp --expected-slots 12584 --out results/reproduction_dfr_length_20261024/train_routes/MTR-DFR
```

```powershell
.venv/Scripts/python.exe tools/stage_native_saved_coordinates.py --routes results/reproduction_dfr_length_20261024/train_routes/MTR-DFR/synthetic_routes.pkl.gz --network resources/network/network.shp --edge-cache resources/edge_cache/edge_cache.pkl.gz --native-source results/reproduction_dfr_length_20261024/native_train/MTR-DFR/release/seed_42_length/road_routes.pkl.gz --for-tstr --out-dir results/reproduction_dfr_length_20261024/train_view/MTR-DFR
```

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/beijing.json --method MTR-DFR --input results/reproduction_dfr_length_20261024/train_view/MTR-DFR/coordinates.pkl --lineage results/reproduction_dfr_length_20261024/native_train/MTR-DFR/lineage.json --metric-protocol audit-v2 --out results/reproduction_dfr_length_20261024/tstr_audit_v2/MTR-DFR/Origin
```

三个方法各输出results.csv和manifest.json。结果中的Real-train使用同一真实训练/测试划分；严格TSTR不与全集回顾性道路预测混为一项。
