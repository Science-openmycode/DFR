# 公共道路 R 适配器

这一组适配器的共同边界是：输入只能是某个 M 已经发布的 `measurement.pkl`，再加上公开道路网络、公开路由索引和公开可执行程序。适配器不会读取 `prepared_data/<dataset>/trajectories.pkl`、`real-reference` 或任何原始轨迹。

## Nearest

`nearest_adapter.py` 将 M 的每个坐标投影到公共路网中距离最近的有向边。它只保留相邻边端点能够连续连接的序列；不做最短路补全、不填充断点。断开的槽位保留 `accepted=false`，并在 `route_manifest.json` 的 `reasons` 中记为 `disconnected`。

```powershell
python run.py route-cell `
  --dataset beijing --m SPRT --r Nearest `
  --measurement synthetic_data/measurements/SPRT/beijing/batch_001 `
  --prepared-data prepared_data/beijing `
  --public-network E:/public/beijing_network/network.shp `
  --edge-cache E:/public/beijing/ordered_portal_route_cache.pkl.gz `
  --out-dir data_results/beijing/batch_001/SPRT/Nearest
```

## STMatch

`public_match_adapter.py` 调用旧实现中已经验证过的 `metric_suites.road_route.run_fmm`，但把匹配器替换为公开的 `stmatch.exe`。输出统一为 `accepted/cpath`，并将外部程序的命令、标准输出、参数和输入哈希写入 manifest。

Windows 运行时目录必须同时包含 `gdal204.dll` 和 `boost_serialization.dll`；`stmatch.exe` 所在目录还必须有它需要的 `FMMLIB.dll`。缺少 DLL 时命令会失败并写出 `status=INVALID` 的 manifest，不会把失败写成 0。

```powershell
python run.py route-cell `
  --dataset beijing --m SPRT --r STMatch `
  --measurement synthetic_data/measurements/SPRT/beijing/batch_001 `
  --prepared-data prepared_data/beijing `
  --public-network E:/public/beijing_network/network.shp `
  --stmatch-executable E:/public/matcher/stmatch.exe `
  --runtime-dir E:/public/matcher_runtime/Library/bin `
  --edge-cache E:/public/beijing/ordered_portal_route_cache.pkl.gz `
  --max-points 32 --radius-m 200 --gps-error-m 50 --candidates 8 `
  --min-observation-share 0.95 `
  --out-dir data_results/beijing/batch_001/SPRT/STMatch
```

## FMM

FMM 与 STMatch 使用同一公共匹配接口，但 FMM 额外要求与道路网络完全对应的 UBODT。UBODT 不能从另一张路网或另一种边编号缓存借用；命令行必须显式提供 `--ubodt`。在 Windows 上，已有复现实验表明 CSV UBODT 比二进制 UBODT 更稳定；构建命令由外部公共资源提供，适配器不会私自生成或替换它。

```powershell
python run.py route-cell `
  --dataset beijing --m SPRT --r FMM `
  --measurement synthetic_data/measurements/SPRT/beijing/batch_001 `
  --prepared-data prepared_data/beijing `
  --public-network E:/public/beijing_network/network.shp `
  --fmm-executable E:/public/matcher/fmm.exe `
  --ubodt E:/public/beijing/ubodt_1000m.txt `
  --runtime-dir E:/public/matcher_runtime/Library/bin `
  --edge-cache E:/public/beijing/ordered_portal_route_cache.pkl.gz `
  --max-points 32 --radius-m 200 --gps-error-m 50 --candidates 8 `
  --min-observation-share 0.95 `
  --out-dir data_results/beijing/batch_001/SPRT/FMM
```

## 与 MTR-DFR 的边界

`MTR-DFR + Origin` 只表示 DFR 自身的原生道路发布。`run.py` 明确拒绝 `MTR-DFR + Nearest/FMM/STMatch/MM2-MDP`，避免把二次匹配结果误称为 DFR 的替换 R。Nearest/FMM/STMatch/MM2-MDP 只用于统计型 M 的 M×R 比较。

## 已验证的 smoke 结果

- Nearest：2 条槽位，生成 `synthetic_routes.pkl.gz`，2 条因最近边序列不连续而保留为 `disconnected`。
- STMatch：2 条槽位，外部程序返回码 0，生成有效 manifest；该 smoke 使用公开北京路网和独立 runtime，2 条轨迹均被匹配器拒绝，原因仍被如实记录。
- FMM：2 条槽位，使用与北京路网哈希一致的 CSV UBODT，外部程序返回码 0，生成有效 manifest；2 条轨迹均被匹配器拒绝，原因仍被如实记录。

这些 smoke 只验证 I/O、公共输入边界和失败记录，不代表完整 17,123 条矩阵已经运行。
