# MTR-DFR 严格 train-only 复现

本文件只描述 MTR-DFR 和四个统计式 baseline 的严格 train-only 流程。真实数据先按固定索引划分为训练集和测试集；合成器只读取训练集，测试集只用于最终下游任务评分。

## 1. 准备划分

```powershell
python commands/reproduce.py prepare-split -- `
  --real C:\data\real_full_frozen.pkl `
  --out-dir C:\runs\strict_split `
  --train-fraction 0.8
```

输出 `train.pkl`、`test.pkl` 和 `split_manifest.json`。

## 2. 生成 MTR-DFR

```powershell
python commands/reproduce.py generate-train-only -- `
  --train-real C:\runs\strict_split\train.pkl `
  --test-real C:\runs\strict_split\test.pkl `
  --record C:\runs\tstr\lineage\dfr.json `
  --out-dir C:\runs\tstr\dfr `
  --generator dfr `
  --edge-cache public_assets\ordered_portal_route_cache.pkl.gz `
  --network public_assets\beijing_network\network.shp `
  --public-slot-count 13698
```

输出道路路线、坐标轨迹和来源记录。`train.pkl` 是唯一私有输入，`test.pkl` 不会进入生成阶段。

## 3. 生成四个统计式 baseline

分别运行 `--generator baseline --method sprt-native`、`privtrace-native`、`dptrajpm-native` 和 `dpstd-native`。每个命令的 `--train-real` 都必须指向同一个训练集，输出目录必须独立。

## 4. 严格 TSTR 评分

```powershell
python commands/reproduce.py run-tstr -- `
  --train-real C:\runs\strict_split\train.pkl `
  --test-real C:\runs\strict_split\test.pkl `
  --synthetic MTR-DFR=C:\runs\tstr\dfr\dfr_coordinates.pkl `
  --synthetic SPRT=C:\runs\tstr\sprt\sprt.pkl `
  --synthetic PrivTrace=C:\runs\tstr\privtrace\privtrace.pkl `
  --synthetic DPTraj-PM=C:\runs\tstr\dptrajpm\dptrajpm.pkl `
  --synthetic DPStd=C:\runs\tstr\dpstd\dpstd.pkl `
  --names MTR-DFR SPRT PrivTrace DPTraj-PM DPStd `
  --split-audit C:\runs\strict_split\split_manifest.json `
  --require-synthesis-lineage `
  --out-dir experiment_results\recomputed\tstr
```

输出 Next-cell、Destination、RoadContinuation 和 Route retrieval 任务结果。测试集只用于最后评估，不用于生成或参数选择。
