# 四个统计 M 的严格 TSTR：逐条执行

工作目录为交付根目录。先完成 reproduction_checked_20261024/COMMANDS_CN.md 中的训练 M 与训练 R。下面只转换已有道路的确定几何，再训练下游模型并在同一真实测试集评分；不会重新合成或重新匹配。

四个 M 的 lineage.json 来自实际训练专用生成，不能用全集发布的 lineage 代替。坐标视图保留全部输出槽位，包括空槽位。指标协议固定 audit-v2。

这些是新批次执行说明，不表示本轮重跑了正式 TSTR。已有冻结成绩继续保留。

## SPRT + Origin


```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method SPRT --router Origin --input results/reproduction_checked_20261024/measurements_train/SPRT/measurement.pkl --lineage results/reproduction_checked_20261024/measurements_train/SPRT/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/SPRT/Origin
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/SPRT/Origin/results.csv 和 manifest.json。

## SPRT + Nearest

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/SPRT/Nearest/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/SPRT/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/SPRT/Nearest
```

生成：results/reproduction_checked_20261024/coordinate_views_train/SPRT/Nearest/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method SPRT --router Nearest --input results/reproduction_checked_20261024/coordinate_views_train/SPRT/Nearest/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/SPRT/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/SPRT/Nearest
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/SPRT/Nearest/results.csv 和 manifest.json。

## SPRT + FMM

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/SPRT/FMM/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/SPRT/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/SPRT/FMM
```

生成：results/reproduction_checked_20261024/coordinate_views_train/SPRT/FMM/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method SPRT --router FMM --input results/reproduction_checked_20261024/coordinate_views_train/SPRT/FMM/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/SPRT/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/SPRT/FMM
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/SPRT/FMM/results.csv 和 manifest.json。

## SPRT + STMatch

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/SPRT/STMatch/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/SPRT/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/SPRT/STMatch
```

生成：results/reproduction_checked_20261024/coordinate_views_train/SPRT/STMatch/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method SPRT --router STMatch --input results/reproduction_checked_20261024/coordinate_views_train/SPRT/STMatch/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/SPRT/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/SPRT/STMatch
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/SPRT/STMatch/results.csv 和 manifest.json。

## SPRT + MM2-MDP

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/SPRT/MM2-MDP/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/SPRT/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/SPRT/MM2-MDP
```

生成：results/reproduction_checked_20261024/coordinate_views_train/SPRT/MM2-MDP/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method SPRT --router MM2-MDP --input results/reproduction_checked_20261024/coordinate_views_train/SPRT/MM2-MDP/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/SPRT/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/SPRT/MM2-MDP
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/SPRT/MM2-MDP/results.csv 和 manifest.json。

## PrivTrace + Origin


```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method PrivTrace --router Origin --input results/reproduction_checked_20261024/measurements_train/PrivTrace/measurement.pkl --lineage results/reproduction_checked_20261024/measurements_train/PrivTrace/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/Origin
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/Origin/results.csv 和 manifest.json。

## PrivTrace + Nearest

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/PrivTrace/Nearest/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/PrivTrace/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/Nearest
```

生成：results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/Nearest/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method PrivTrace --router Nearest --input results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/Nearest/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/PrivTrace/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/Nearest
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/Nearest/results.csv 和 manifest.json。

## PrivTrace + FMM

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/PrivTrace/FMM/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/PrivTrace/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/FMM
```

生成：results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/FMM/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method PrivTrace --router FMM --input results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/FMM/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/PrivTrace/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/FMM
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/FMM/results.csv 和 manifest.json。

## PrivTrace + STMatch

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/PrivTrace/STMatch/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/PrivTrace/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/STMatch
```

生成：results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/STMatch/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method PrivTrace --router STMatch --input results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/STMatch/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/PrivTrace/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/STMatch
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/STMatch/results.csv 和 manifest.json。

## PrivTrace + MM2-MDP

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/PrivTrace/MM2-MDP/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/PrivTrace/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/MM2-MDP
```

生成：results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/MM2-MDP/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method PrivTrace --router MM2-MDP --input results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/MM2-MDP/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/PrivTrace/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/MM2-MDP
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/MM2-MDP/results.csv 和 manifest.json。

## DPTraj-PM + Origin


```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router Origin --input results/reproduction_checked_20261024/measurements_train/DPTraj-PM/measurement.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPTraj-PM/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/Origin
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/Origin/results.csv 和 manifest.json。

## DPTraj-PM + Nearest

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPTraj-PM/Nearest/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPTraj-PM/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/Nearest
```

生成：results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/Nearest/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router Nearest --input results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/Nearest/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPTraj-PM/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/Nearest
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/Nearest/results.csv 和 manifest.json。

## DPTraj-PM + FMM

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPTraj-PM/FMM/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPTraj-PM/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/FMM
```

生成：results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/FMM/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router FMM --input results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/FMM/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPTraj-PM/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/FMM
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/FMM/results.csv 和 manifest.json。

## DPTraj-PM + STMatch

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPTraj-PM/STMatch/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPTraj-PM/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/STMatch
```

生成：results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/STMatch/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router STMatch --input results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/STMatch/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPTraj-PM/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/STMatch
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/STMatch/results.csv 和 manifest.json。

## DPTraj-PM + MM2-MDP

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPTraj-PM/MM2-MDP/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPTraj-PM/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/MM2-MDP
```

生成：results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/MM2-MDP/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router MM2-MDP --input results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/MM2-MDP/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPTraj-PM/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/MM2-MDP
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/MM2-MDP/results.csv 和 manifest.json。

## DPStd + Origin


```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method DPStd --router Origin --input results/reproduction_checked_20261024/measurements_train/DPStd/measurement.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPStd/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPStd/Origin
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPStd/Origin/results.csv 和 manifest.json。

## DPStd + Nearest

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPStd/Nearest/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPStd/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPStd/Nearest
```

生成：results/reproduction_checked_20261024/coordinate_views_train/DPStd/Nearest/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method DPStd --router Nearest --input results/reproduction_checked_20261024/coordinate_views_train/DPStd/Nearest/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPStd/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPStd/Nearest
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPStd/Nearest/results.csv 和 manifest.json。

## DPStd + FMM

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPStd/FMM/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPStd/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPStd/FMM
```

生成：results/reproduction_checked_20261024/coordinate_views_train/DPStd/FMM/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method DPStd --router FMM --input results/reproduction_checked_20261024/coordinate_views_train/DPStd/FMM/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPStd/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPStd/FMM
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPStd/FMM/results.csv 和 manifest.json。

## DPStd + STMatch

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPStd/STMatch/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPStd/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPStd/STMatch
```

生成：results/reproduction_checked_20261024/coordinate_views_train/DPStd/STMatch/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method DPStd --router STMatch --input results/reproduction_checked_20261024/coordinate_views_train/DPStd/STMatch/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPStd/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPStd/STMatch
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPStd/STMatch/results.csv 和 manifest.json。

## DPStd + MM2-MDP

先将已有道路编号转为确定几何，不添加道路：

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPStd/MM2-MDP/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPStd/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPStd/MM2-MDP
```

生成：results/reproduction_checked_20261024/coordinate_views_train/DPStd/MM2-MDP/coordinates.pkl 及其来源 manifest。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config reproduction_checked_20261024/config.json --method DPStd --router MM2-MDP --input results/reproduction_checked_20261024/coordinate_views_train/DPStd/MM2-MDP/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPStd/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPStd/MM2-MDP
```

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPStd/MM2-MDP/results.csv 和 manifest.json。
