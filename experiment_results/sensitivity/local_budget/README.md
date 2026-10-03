# DFR 隐私预算敏感性（五种子）

本目录包含北京数据集上 MTR-DFR 在 ε = 1/5、2/5、7/10、1、7/5、2、3 下的五种子结果（20260719--20260723）。每个点均由生成器重新生成固定数量的合成轨迹，再运行统一 DFR 评估器得到 9 项指标。

## 结果文件

- `metrics_long.csv`：35 个运行点的逐指标长表；
- `metrics_summary.csv`：每个预算的均值、标准差和 95% seed-bootstrap 区间；
- `dfr_epsilon_sensitivity_5seed.png/pdf`：九项指标的预算曲线；
- `aggregation_manifest.json`：预算、种子、指标和结果分类记录。

## 复现命令

从仓库根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File commands/run_local_dfr_budget_sweep.ps1 -Seeds 20260719,20260720,20260721,20260722,20260723 -Epsilons 0.2,0.4,0.7,1.0,1.4,2.0,3.0 -Resume
python commands/aggregate_budget_sweep.py
```

预算扫描是研究性敏感性实验，manifest 明确标记为 `RESEARCH_ONLY_REPRODUCIBLE_NOISE_DO_NOT_RELEASE`；它不表示把七个预算结果同时作为一次正式隐私发布。
