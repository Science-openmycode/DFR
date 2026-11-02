# DFR 全集原生结果的独立评分

按仓库根 README 第8步准备配置，并在同一 PowerShell 窗口执行本页。本页随仓库提供，不由运行命令生成。`configs/experiments/` 是当前数据的配置目录；`results/` 下的名称以北京复现为例，不是必须的文件名。更改结果目录时，将本页及依赖文档中对应的 `--out`、`--input`、`--source` 等路径同步替换；不要改算法名、预算或种子来代替改文件名。Porto 使用另一个检出目录，命令相同。

在部署根目录运行，先完成 REPRODUCE_DFR_LENGTH_20261024_CN.md 的全集生成并确认正常退出、私有 lineage 中 status=DONE。当前正式分支为 seed_42_length。以下使用明确的原生节点对和其指标缓存；不重新匹配，不混用物理路网节点编号。

## 1. 道路合法性与路线选择

下面的原命令直接支持原生节点对，无需先改成其它入口。若一个节点对有多个道路编号，只在公共图有向几何、物理端点及评分缓存端点一致时采用最小编号；确有不同几何或缺少证据仍拒绝。`--source-cache` 必须是生成这份 DFR 输出时使用的节点命名空间缓存，不能仅因文件名相同就替换。道路任务入口复核同一图及其附属文件，并使用相同转换规则；物理结构和坐标评分的命令保持如下顺序，全部槽位不变。

```powershell
.venv/Scripts/python.exe evaluate.py --config configs/experiments/configs/beijing.json --method MTR-DFR --router Origin --representation node-pairs --source-cache "$MetricCache" --input results/reproduction_dfr_length_20261024/native/MTR-DFR/seed_42_length/road_routes.pkl.gz --out results/reproduction_dfr_length_20261024/scores/MTR-DFR/Origin
```

预期输出 metrics.json、metrics.csv、manifest.json，记录真实输入、原生合成数据及评分缓存来源。全部15730个合成槽位参与评分，不筛选合成成功子集。

## 2. 物理轨迹结构

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config configs/experiments/configs/beijing.json --method MTR-DFR --router Origin --input results/reproduction_dfr_length_20261024/native/MTR-DFR/seed_42_length/road_routes.pkl.gz --out results/reproduction_dfr_length_20261024/physical_scores/MTR-DFR/Origin
```

输出物理结构评分及 input_binding.json。沿用原协议的全量OD质量与分层序列样本上限20，不将抽样序列部分称为全部逐对比较。

## 3. 回顾性下一道路与道路选择任务

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config configs/experiments/configs/beijing.json --method MTR-DFR --router Origin --input results/reproduction_dfr_length_20261024/native/MTR-DFR/seed_42_length/road_routes.pkl.gz --score-manifest results/reproduction_dfr_length_20261024/scores/MTR-DFR/Origin/manifest.json --out results/reproduction_dfr_length_20261024/road_tasks/MTR-DFR/Origin
```

第3步依赖第1步的真实评分来源。此处是全量发布的回顾性道路任务，不冒充严格TSTR。严格TSTR必须另外使用训练专用生成结果和对应lineage。

## 4. DFR 坐标统计

先将节点对转换为同一道路的编号，再取确定几何；不运行匹配器：

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/reproduction_dfr_length_20261024/native/MTR-DFR/seed_42_length/road_routes.pkl.gz --source-cache "$MetricCache" --network "$Network" --expected-slots $FullSlots --out results/reproduction_dfr_length_20261024/full_routes/MTR-DFR
.venv/Scripts/python.exe evaluate_coordinates.py --config configs/experiments/configs/beijing.json --method MTR-DFR --router Origin --input results/reproduction_dfr_length_20261024/full_routes/MTR-DFR/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/reproduction_dfr_length_20261024/coordinate_scores_audit_v2/MTR-DFR/Origin
```

输出坐标统计metrics.json及来源manifest。

## 5. MTNet 全集登记与四类评分

先完成全集MTNet的训练和原生生成：

```powershell
.venv/Scripts/python.exe register_mtnet.py --config configs/experiments/configs/beijing.json --source results/reproduction_native_20261024/full/MTNet_deployment/native_release --preparation results/reproduction_native_20261024/full/MTNet_prepared/full_preparation_manifest.json --model results/reproduction_native_20261024/full/MTNet_deployment/trained/model.pt --out results/reproduction_native_20261024/full/MTNet_routes
.venv/Scripts/python.exe evaluate.py --config configs/experiments/configs/beijing.json --method MTNet --router Origin --input results/reproduction_native_20261024/full/MTNet_routes/synthetic_routes.pkl.gz --out results/reproduction_native_20261024/scores/MTNet/Origin
.venv/Scripts/python.exe evaluate_coordinates.py --config configs/experiments/configs/beijing.json --method MTNet --router Origin --input results/reproduction_native_20261024/full/MTNet_routes/synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results/reproduction_native_20261024/coordinate_scores_audit_v2/MTNet/Origin
.venv/Scripts/python.exe evaluate_physical.py --config configs/experiments/configs/beijing.json --method MTNet --router Origin --input results/reproduction_native_20261024/full/MTNet_routes/synthetic_routes.pkl.gz --out results/reproduction_native_20261024/physical_scores/MTNet/Origin
.venv/Scripts/python.exe evaluate_road_tasks.py --config configs/experiments/configs/beijing.json --method MTNet --router Origin --input results/reproduction_native_20261024/full/MTNet_routes/synthetic_routes.pkl.gz --score-manifest results/reproduction_native_20261024/scores/MTNet/Origin/manifest.json --out results/reproduction_native_20261024/road_tasks/MTNet/Origin
```

依次输出原生道路记录、道路指标、坐标统计、物理结构及道路任务；所有评分读取同一全集生成结果。

## 6. DPMM 全集坐标统计

当前DPMM导出坐标数组。按其输入索引保留成功数组，缺失槽位置空，不再匹配或插入路线：

```powershell
.venv/Scripts/python.exe tools/stage_dpmm_evaluation_slots.py --release results/reproduction_native_20261024/full/DPMM/dpmm.pkl --manifest results/reproduction_native_20261024/full/DPMM/dpmm.json --out-dir results/reproduction_native_20261024/full/DPMM_view
.venv/Scripts/python.exe evaluate_coordinates.py --config configs/experiments/configs/beijing.json --method DPMM --router Origin --input results/reproduction_native_20261024/full/DPMM_view/coordinates.pkl --metric-protocol audit-v2 --out results/reproduction_native_20261024/coordinate_scores_audit_v2/DPMM/Origin
```

输出保留全集槽位的coordinates.pkl及统计评分。没有原生道路ID的指标保留缺失，不通过额外匹配填充。
