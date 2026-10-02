# MTR-DFR 实验事实表

本表记录当前仓库已经保存或已经执行的实验。未完成表示目录有入口或部分结果，但还没有形成完整统一批次。

| 实验 | 协议 | 主要指标 | 结果/状态 |
|---|---|---|---|
| MTR-DFR 主发布 | 北京 17,123 条，5 个种子，17,123 固定槽位 | RoadYield、DirValid、DemandFid、Edge/Turn F1、BranchCPC、ExitAcc、BTF、RC/Edge/Turn/Family CPC、ODPF、结构、TSTR | 已完成 |
| MTR 框架提升 | 四个统计基线，Native 与公共道路路由配对 | RoadYield、BTF、FamilyCPC、ODPF96/384 | 已完成 |
| M×R 矩阵 | 多种测量与 Native/FMM/STMatch/Family 路由组合 | BTF、FamilyCPC、ODPF96/384、RoadYield | 已完成 |
| 算法级消融 | endpoint、route-family、matched-router 组合 | BTF、RC-CPC、EdgeCPC、TurnCPC、FamilyCPC | 已完成 |
| 隐私攻击 | MTR-GSRT、DPMM、PUTS、MTNet | DOMIAS、GDA-MIA、Origin、Route | 已完成 |
| 严格 train-only TSTR | 13,698 训练，3,425 未见测试 | Next-cell、Destination、RoadContinuation、Route retrieval | 已完成 |
| 逐轨迹结构 | 真实与 DFR 逐条比较 | Backbone、Turn、Closed、RepeatedEdge、Length retention | 已完成 |
| Porto/SF | 跨城市配置和命令 | 生成、评估、作图 | 主冻结表未收录；补充结果见 `experiment_results/rebuttal_supplement/q6_multicity_five_seed/` |
| epsilon 曲线 | 北京多预算配置 | 预算—指标曲线 | 补充结果见 `experiment_results/rebuttal_supplement/q6_low_epsilon/`；标记为研究性预算诊断 |
| WitnessValid | DFR 隔离产物 | 消费者可见 witness | 未完成，当前记录为 NOT_SERIALIZED |
| Oldenburg | 独立模拟道路图，500,000 source | 统计、道路、路线、扩展性 | full-scale 指标摘要见 `experiment_results/rebuttal_supplement/oldenburg_full_scale/`；原始二进制不随仓库发布 |

## OpenReview 补充实验

审稿回复中已经完成、但不替换北京主冻结结果的补充批次统一放在
`experiment_results/rebuttal_supplement/`，并由
`plotting/plot_rebuttal_supplement.py` 重画：

- `q5_partition_sensitivity/`：K=48--1024 的区域分辨率敏感性；
- `q6_multicity_five_seed/`：Porto/SF 五种子汇总；
- `q6_low_epsilon/`：1/5--3 的预算曲线、query-family 噪声和 fallback；
- `portal_fiber_ablation/`：MTR-GSRT 与 No Portal unit；
- `oldenburg_full_scale/`：500,000 条 source/output 的指标和协议摘要。

这些文件是补充研究结果，使用前必须按照目录 README 区分 MTR-GSRT、MTR-DFR、主冻结批次和研究性诊断批次。

## DFR 冻结代表值

| 指标 | 值 |
|---|---:|
| RoadYield / DirValid | 1.0000 / 1.0000 |
| DemandFid | 0.8964 |
| EdgeF1 / TurnF1 | 0.7559 / 0.7274 |
| BranchCPC / ExitAcc | 0.7701 / 0.7760 |
| BTF / RC-CPC | 0.4958 / 0.4919 |
| EdgeCPC / TurnCPC / FamilyCPC | 0.5566 / 0.5442 / 0.4192 |
| ODPF96 / ODPF384 | 0.4377 / 0.2476 |
| BackboneLengthRetention | 0.9809 |
| ClosedLengthRetention / RepeatedEdgeRetention | 0.0120 / 0.0010 |
| NextCellHit@1 / NextCellMRR | 0.7376 / 0.8043 |
| DestinationHit@5 / RoadContinuationHit@1 | 0.3715 / 0.7999 |
| RouteRetrievalNDCG@5 | 0.4448 |

## 复现实验入口

```powershell
python commands/reproduce.py generate-main ...
python commands/reproduce.py generate-baselines ...
python commands/reproduce.py run-framework ...
python commands/reproduce.py run-profile ...
python commands/reproduce.py run-mr ...
python commands/reproduce.py run-ablation ...
python commands/reproduce.py run-privacy ...
python commands/reproduce.py run-tstr ...
python commands/reproduce.py run-physical ...
python commands/reproduce.py plot ...
```

完整参数和预期输出见根目录 `README_CN.md` 与 `docs/COMMAND_PARAMETERS_CN.md`。
