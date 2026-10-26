# DFR 全集原生结果的独立评分

在部署根目录运行，先完成 REPRODUCE_DFR_LENGTH_20261024_CN.md 的全集生成并确认正常退出、私有 lineage 中 status=DONE。当前正式分支为 seed_42_length。以下使用明确的原生节点对和其指标缓存；不重新匹配，不混用物理路网节点编号。

## 1. 道路合法性与路线选择

```powershell
.venv/Scripts/python.exe evaluate.py --config configs/beijing.json --method MTR-DFR --router Origin --representation node-pairs --source-cache resources/metric_cache/metric_cache.pkl.gz --input results/reproduction_dfr_length_20261024/native/MTR-DFR/seed_42_length/road_routes.pkl.gz --out results/reproduction_dfr_length_20261024/scores/MTR-DFR/Origin
```

预期输出 metrics.json、metrics.csv、manifest.json，记录真实输入、原生合成数据及评分缓存来源。全部15730个合成槽位参与评分，不筛选合成成功子集。

## 2. 物理轨迹结构

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config configs/beijing.json --method MTR-DFR --router Origin --input results/reproduction_dfr_length_20261024/native/MTR-DFR/seed_42_length/road_routes.pkl.gz --out results/reproduction_dfr_length_20261024/physical_scores/MTR-DFR/Origin
```

输出物理结构评分及 input_binding.json。沿用原协议的全量OD质量与分层序列样本上限20，不将抽样序列部分称为全部逐对比较。

## 3. 回顾性下一道路与道路选择任务

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config configs/beijing.json --method MTR-DFR --router Origin --input results/reproduction_dfr_length_20261024/native/MTR-DFR/seed_42_length/road_routes.pkl.gz --score-manifest results/reproduction_dfr_length_20261024/scores/MTR-DFR/Origin/manifest.json --out results/reproduction_dfr_length_20261024/road_tasks/MTR-DFR/Origin
```

第3步依赖第1步的真实评分来源。此处是全量发布的回顾性道路任务，不冒充严格TSTR。严格TSTR必须另外使用训练专用生成结果和对应lineage。
