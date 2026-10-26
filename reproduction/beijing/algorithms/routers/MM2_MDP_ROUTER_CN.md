# MM2-MDP R 适配器

这个适配器把 `measurement.pkl` 中已经发布的坐标轨迹交给官方 MM2-MDP Value-Iteration 实现，再把 MM2 的道路编号转换成统一评估器使用的 `accepted/cpath` 路由记录。

## 输入边界

- `measurement.pkl`：某个 M 的输出；输入记录按槽位编号为 `0..n-1`。
- `--executable`：官方 MM2 可执行文件。
- `--network`：只含公共道路的 MM2 prepared network 目录。
- `--edge-cache`：公共评估缓存，必须包含 `edge_nodes`。

不读取 `prepared_data/trajectories.pkl`、`--real-reference` 或任何真实轨迹。MTR-DFR 的原生道路结果不能调用这个适配器做二次匹配；`run.py` 会拒绝 `MTR-DFR + MM2-MDP`。

## 命令行

```powershell
python run.py route-cell `
  --dataset beijing `
  --m SPRT `
  --r MM2-MDP `
  --measurement synthetic_data/measurements/SPRT/beijing/batch_001 `
  --prepared-data prepared_data/beijing `
  --mm2-executable E:/public/mm2/bin/map_matching_2.exe `
  --mm2-network E:/public/mm2/beijing/network `
  --edge-cache E:/public/road_cache/ordered_portal_route_cache.pkl.gz `
  --input-srs EPSG:4326 `
  --tracks-srs EPSG:32650 `
  --network-srs EPSG:32650 `
  --max-points 32 `
  --out-dir data_results/beijing/batch_001/SPRT/MM2-MDP
```

`--input-srs` 是 M 坐标的 CRS；当前统一 M 坐标为 WGS84 `[latitude, longitude]`。`--tracks-srs` 必须与 prepared network 的坐标系一致；MM2 最终接收数字 EPSG（例如 `EPSG:32650` 会写成 `32650`）。`--max-points` 保留起终点，并在中间均匀抽样，默认 32，与既有路线评分协议一致。

## 输出

```text
data_results/.../SPRT/MM2-MDP/
├─ mm2_tracks.csv             # 从 M 输出导出的 WKT，不含真实数据
├─ mm2_run/matches.csv        # MM2 原生结果
├─ synthetic_routes.pkl.gz    # 统一 accepted/cpath 结果
├─ mm2_command.json
├─ mm2_stdout.log
├─ mm2_stderr.log
└─ route_manifest.json
```

`route_manifest.json` 保存 M、MM2 可执行文件、公共网络、edge cache 的哈希、坐标系、抽样上限、命令、槽位总数和失败原因计数。`aborted`、未知边、断开的边序列不会被补齐，分别记录为 `aborted`、`unknown_edge`、`disconnected`，对应槽位的 `accepted=false`、`cpath=[]`。

## 已验证范围

隔离目录中已用 2 条北京 SPRT M 输出进行端到端 smoke test：MM2 返回 2/2 条记录，两个 `cpath` 均通过公共 `edge_nodes` 连通性验证，并可被既有 `normalize_routes` 读取。这个 smoke test 不代表 17,123 条全量矩阵已经运行；全量运行需要提供相应数据集的公共 prepared network、edge cache 和官方 MM2 二进制。
