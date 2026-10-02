# Rebuttal 补充实验结果

本目录收录 OpenReview 审稿回复中已经完成、但不属于北京主冻结批次的补充实验。它们是研究性评估结果，不替换 `experiment_results/frozen/` 中的主结果。

## 目录

```text
rebuttal_supplement/
├─ q5_partition_sensitivity/
│  ├─ q5_partition_sensitivity_detailed.csv
│  ├─ q5_partition_sensitivity_summary.csv
│  ├─ q5_partition_sensitivity_manifest.json
│  └─ q5_partition_granularity_sensitivity.pdf/png
├─ q6_multicity_five_seed/
│  ├─ q6_multicity_five_seed_detailed.csv
│  ├─ q6_multicity_five_seed_summary.csv
│  └─ manifest.json
├─ q6_low_epsilon/
│  ├─ q6_full_release_utility_detailed.csv
│  ├─ q6_full_release_utility_summary.csv
│  ├─ q6_query_family_summary.csv
│  ├─ q6_all_query_blocks_detailed.csv
│  ├─ q6_complete_low_epsilon_manifest.json
│  └─ q6_complete_low_epsilon_audit.pdf/png
├─ portal_fiber_ablation/
│  ├─ ablation.csv
│  ├─ portal_fiber_ablation.csv
│  └─ q5_portal_component_ablation.pdf/png
└─ oldenburg_full_scale/
   ├─ oldenburg_full_scale_manifest.json
   ├─ metrics_full.csv/json
   ├─ same_beijing_metrics.csv/json
   ├─ route_metrics_same_beijing.json
   └─ README_full_source.md
```

## 1. Q5 分区分辨率敏感性

`q5_partition_sensitivity_summary.csv` 覆盖 K=48 到 K=1024 的 nested quotient partition，记录 route-choice CPC、NDCG、Top-1、噪声质量、context coverage 和 95% 区间。图表直接使用该 CSV：

```powershell
python plotting/plot_rebuttal_supplement.py partition `
  --input experiment_results/rebuttal_supplement/q5_partition_sensitivity/q5_partition_sensitivity_summary.csv `
  --out-dir experiment_results/rebuttal_supplement/figures
```

这些结果回答“区域分辨率改变时路线选择保真度如何变化”，不改变正式 MTR-GSRT 预算或生产账本。

## 2. Porto 与 San Francisco 五种子

`q6_multicity_five_seed_detailed.csv` 保存 20260719--20260723 五个种子的逐次结果，`q6_multicity_five_seed_summary.csv` 保存均值和置信区间。它覆盖 Grid、Trip、Length、OD、RoadSeg、Next-region、RouteMRR、WitnessValid、生成时间和 fallback 数量。

```powershell
python plotting/plot_rebuttal_supplement.py multicity `
  --input-dir experiment_results/rebuttal_supplement/q6_multicity_five_seed `
  --out-dir experiment_results/rebuttal_supplement/figures
```

## 3. 隐私预算曲线与 Portal-Fiber 噪声

`q6_low_epsilon` 覆盖 ε=1/5、2/5、7/10、1、7/5、2、3，每个预算五个种子；同时记录 query-family CPC/JSD、噪声主导质量、fallback、路线指标和生成时间。

```powershell
python plotting/plot_rebuttal_supplement.py low-epsilon `
  --input-dir experiment_results/rebuttal_supplement/q6_low_epsilon `
  --out-dir experiment_results/rebuttal_supplement/figures
```

该批次的 manifest 标明 `INTERNAL_PRIVATE_UTILITY_DIAGNOSTIC_NOT_A_DP_RELEASE`。它用于分析预算对效用的影响，不表示把七个预算发布合并为一次正式 DP 发布。

## 4. Portal-Fiber 消融

`portal_fiber_ablation.csv` 比较完整 MTR-GSRT 与移除 Portal unit 的结果。该消融保持其余配置不变，直接比较 Grid、Trip、Length、WitnessValid、RC-CPC、RC-NDCG、NextRoadAcc 和 NextRoadNLL。

```powershell
python plotting/plot_rebuttal_supplement.py portal-ablation `
  --input experiment_results/rebuttal_supplement/portal_fiber_ablation/portal_fiber_ablation.csv `
  --out-dir experiment_results/rebuttal_supplement/figures
```

## 5. Oldenburg 500,000 条全量实验

`oldenburg_full_scale_manifest.json` 和指标文件保存 500,000 条 source、500,000 条 output 的 full-scale 诊断。由于原始数据和合成 release 合计超过 1 GB，本公开仓库不复制二进制轨迹文件；manifest 记录 release 版本、公共图规模、预算、指标文件和外部数据位置。使用者需要按 `README_full_source.md` 准备外部文件后运行解码器。

Oldenburg 是模拟道路网络数据，不应写成真实 GPS 城市数据。旧的 20,000 条坐标不兼容样本不属于本目录。

## 与主冻结结果的关系

- 主论文北京结果仍读取 `experiment_results/frozen/`；
- 本目录只追加审稿回复补充证据；
- Q5/Q6 结果的代码版本、输入哈希和协议 manifest 保存在原始隔离批次中；
- 在把这些补充结果写入论文前，应先统一三城市指标、adapter 和 release 命名，不能把不同版本的 MTR-GSRT、MTR-DFR 数值混写。
