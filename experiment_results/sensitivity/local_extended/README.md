# DFR 本地断点验证

`k96_profile_seed20261003.csv` 是本地 Python 3.13 环境使用 DFR 公开入口生成 (K=96)、17,123 个固定槽位后的完整 profile 结果。它与云端正式敏感性批次使用不同种子，不能与云端批次合并计算置信区间，也不替代云端 (K=96) 结果。

生成 manifest 位于 `dfr_resolution_k96_seed20261003/seed_20261003_length/manifest.json`，道路输出为 `road_routes.pkl.gz`，坐标输出为 `k96_coordinates.pkl`。该断点的路由和 witness 检查均通过。
