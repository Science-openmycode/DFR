# DFR 本地断点验证

`k96_profile_seed20261003.csv` 是本地 Python 3.13 环境使用 DFR 公开入口生成 (K=96)、17,123 个固定槽位后的完整 profile 结果。它与云端正式敏感性批次使用不同种子，不能与云端批次合并计算置信区间，也不替代云端 (K=96) 结果。

生成 manifest 位于 `dfr_resolution_k96_seed20261003/seed_20261003_length/manifest.json`，道路输出为 `road_routes.pkl.gz`，坐标输出为 `k96_coordinates.pkl`。该断点的路由和 witness 检查均通过。

同一独立种子还完成了 `K=48,80,112,128,160,192,224,256,288,320,352,384`。完整 13 点汇总（含 K=96）在 `dfr_resolution_local_extended_summary.csv`，对应 manifest 的 SHA-256 在 `dfr_resolution_local_extended_manifests.json`。其中新增点的主要 profile 数值如下：

| K | TripSim | GridSim | LengthSim | NextRoadAcc | RouteMRR | RouteBest5F1 |
|---:|---:|---:|---:|---:|---:|---:|
| 96 | 0.7734 | 0.7902 | 0.9484 | 0.5544 | 0.4900 | 0.5041 |
| 128 | 0.7729 | 0.7913 | 0.9481 | 0.5701 | 0.5236 | 0.5336 |
| 192 | 0.7828 | 0.7890 | 0.9581 | 0.5544 | 0.4969 | 0.5185 |
| 256 | 0.7727 | 0.7890 | 0.9452 | 0.5511 | 0.4760 | 0.5079 |
| 384 | 0.7808 | 0.7910 | 0.9538 | 0.5595 | 0.4909 | 0.5323 |

每个点的 `RoadYield`、`DirValid`、`WitnessValid` 均为 1。该表只描述本地种子 20261003，不与云端种子 20260721 的六点表合并。
