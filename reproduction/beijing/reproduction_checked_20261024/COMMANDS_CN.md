# 四个统计M：新批次独立命令清单

在部署根目录执行。先设置当前终端编码；每条实验命令独立运行，不通过队列替换外层入口。

```powershell
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
```

全量发布用于统计/道路保真评价；训练发布只为后续严格TSTR准备，不能拿全量评分当TSTR。
此清单覆盖四个统计M及五个R，不包括DFR/DPMM/MTNet原生生成、训练lineage登记、攻击、K/预算及作图。
这是待执行的新批次计划，不是已完成的实验记录。M只生成一次，五个R读取同一份测量。

## SPRT/full/M

依赖：冻结输入与公共资源

```powershell
.venv/Scripts/python.exe synthesize.py --config reproduction_checked_20261024/config.json --method SPRT --out results\reproduction_checked_20261024\measurements\SPRT
```

预期输出：`results\reproduction_checked_20261024\measurements\SPRT\measurement.pkl`、`results\reproduction_checked_20261024\measurements\SPRT\measurement_manifest.json`

## SPRT/full/Origin/R

依赖：SPRT/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method SPRT --router Origin --input results\reproduction_checked_20261024\measurements\SPRT --out results\reproduction_checked_20261024\routes\SPRT\Origin
```

预期输出：`results\reproduction_checked_20261024\routes\SPRT\Origin\synthetic_coordinates.pkl`、`results\reproduction_checked_20261024\routes\SPRT\Origin\route_manifest.json`

## SPRT/full/Origin/coordinates

依赖：SPRT/full/Origin/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method SPRT --router Origin --input results\reproduction_checked_20261024\routes\SPRT\Origin\synthetic_coordinates.pkl --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\Origin
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\Origin\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\Origin\manifest.json`

## SPRT/full/Nearest/R

依赖：SPRT/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method SPRT --router Nearest --input results\reproduction_checked_20261024\measurements\SPRT --out results\reproduction_checked_20261024\routes\SPRT\Nearest
```

预期输出：`results\reproduction_checked_20261024\routes\SPRT\Nearest\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\SPRT\Nearest\route_manifest.json`

## SPRT/full/Nearest/coordinates

依赖：SPRT/full/Nearest/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method SPRT --router Nearest --input results\reproduction_checked_20261024\routes\SPRT\Nearest\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\Nearest
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\Nearest\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\Nearest\manifest.json`

## SPRT/full/Nearest/roads

依赖：SPRT/full/Nearest/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method SPRT --router Nearest --input results\reproduction_checked_20261024\routes\SPRT\Nearest\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\SPRT\Nearest
```

预期输出：`results\reproduction_checked_20261024\scores\SPRT\Nearest\metrics.json`、`results\reproduction_checked_20261024\scores\SPRT\Nearest\manifest.json`

## SPRT/full/Nearest/physical

依赖：SPRT/full/Nearest/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method SPRT --router Nearest --input results\reproduction_checked_20261024\routes\SPRT\Nearest\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\SPRT\Nearest
```

预期输出：`results\reproduction_checked_20261024\physical_scores\SPRT\Nearest\results.csv`、`results\reproduction_checked_20261024\physical_scores\SPRT\Nearest\input_binding.json`

## SPRT/full/Nearest/road_tasks

依赖：SPRT/full/Nearest/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method SPRT --router Nearest --input results\reproduction_checked_20261024\routes\SPRT\Nearest\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\SPRT\Nearest\manifest.json --out results\reproduction_checked_20261024\road_tasks\SPRT\Nearest
```

预期输出：`results\reproduction_checked_20261024\road_tasks\SPRT\Nearest\metrics.json`、`results\reproduction_checked_20261024\road_tasks\SPRT\Nearest\manifest.json`

## SPRT/full/FMM/R

依赖：SPRT/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method SPRT --router FMM --input results\reproduction_checked_20261024\measurements\SPRT --out results\reproduction_checked_20261024\routes\SPRT\FMM
```

预期输出：`results\reproduction_checked_20261024\routes\SPRT\FMM\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\SPRT\FMM\route_manifest.json`

## SPRT/full/FMM/coordinates

依赖：SPRT/full/FMM/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method SPRT --router FMM --input results\reproduction_checked_20261024\routes\SPRT\FMM\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\FMM
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\FMM\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\FMM\manifest.json`

## SPRT/full/FMM/roads

依赖：SPRT/full/FMM/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method SPRT --router FMM --input results\reproduction_checked_20261024\routes\SPRT\FMM\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\SPRT\FMM
```

预期输出：`results\reproduction_checked_20261024\scores\SPRT\FMM\metrics.json`、`results\reproduction_checked_20261024\scores\SPRT\FMM\manifest.json`

## SPRT/full/FMM/physical

依赖：SPRT/full/FMM/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method SPRT --router FMM --input results\reproduction_checked_20261024\routes\SPRT\FMM\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\SPRT\FMM
```

预期输出：`results\reproduction_checked_20261024\physical_scores\SPRT\FMM\results.csv`、`results\reproduction_checked_20261024\physical_scores\SPRT\FMM\input_binding.json`

## SPRT/full/FMM/road_tasks

依赖：SPRT/full/FMM/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method SPRT --router FMM --input results\reproduction_checked_20261024\routes\SPRT\FMM\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\SPRT\FMM\manifest.json --out results\reproduction_checked_20261024\road_tasks\SPRT\FMM
```

预期输出：`results\reproduction_checked_20261024\road_tasks\SPRT\FMM\metrics.json`、`results\reproduction_checked_20261024\road_tasks\SPRT\FMM\manifest.json`

## SPRT/full/STMatch/R

依赖：SPRT/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method SPRT --router STMatch --input results\reproduction_checked_20261024\measurements\SPRT --out results\reproduction_checked_20261024\routes\SPRT\STMatch
```

预期输出：`results\reproduction_checked_20261024\routes\SPRT\STMatch\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\SPRT\STMatch\route_manifest.json`

## SPRT/full/STMatch/coordinates

依赖：SPRT/full/STMatch/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method SPRT --router STMatch --input results\reproduction_checked_20261024\routes\SPRT\STMatch\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\STMatch
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\STMatch\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\STMatch\manifest.json`

## SPRT/full/STMatch/roads

依赖：SPRT/full/STMatch/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method SPRT --router STMatch --input results\reproduction_checked_20261024\routes\SPRT\STMatch\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\SPRT\STMatch
```

预期输出：`results\reproduction_checked_20261024\scores\SPRT\STMatch\metrics.json`、`results\reproduction_checked_20261024\scores\SPRT\STMatch\manifest.json`

## SPRT/full/STMatch/physical

依赖：SPRT/full/STMatch/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method SPRT --router STMatch --input results\reproduction_checked_20261024\routes\SPRT\STMatch\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\SPRT\STMatch
```

预期输出：`results\reproduction_checked_20261024\physical_scores\SPRT\STMatch\results.csv`、`results\reproduction_checked_20261024\physical_scores\SPRT\STMatch\input_binding.json`

## SPRT/full/STMatch/road_tasks

依赖：SPRT/full/STMatch/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method SPRT --router STMatch --input results\reproduction_checked_20261024\routes\SPRT\STMatch\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\SPRT\STMatch\manifest.json --out results\reproduction_checked_20261024\road_tasks\SPRT\STMatch
```

预期输出：`results\reproduction_checked_20261024\road_tasks\SPRT\STMatch\metrics.json`、`results\reproduction_checked_20261024\road_tasks\SPRT\STMatch\manifest.json`

## SPRT/full/MM2-MDP/R

依赖：SPRT/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method SPRT --router MM2-MDP --input results\reproduction_checked_20261024\measurements\SPRT --out results\reproduction_checked_20261024\routes\SPRT\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\routes\SPRT\MM2-MDP\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\SPRT\MM2-MDP\route_manifest.json`

## SPRT/full/MM2-MDP/coordinates

依赖：SPRT/full/MM2-MDP/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method SPRT --router MM2-MDP --input results\reproduction_checked_20261024\routes\SPRT\MM2-MDP\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\MM2-MDP\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\SPRT\MM2-MDP\manifest.json`

## SPRT/full/MM2-MDP/roads

依赖：SPRT/full/MM2-MDP/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method SPRT --router MM2-MDP --input results\reproduction_checked_20261024\routes\SPRT\MM2-MDP\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\SPRT\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\scores\SPRT\MM2-MDP\metrics.json`、`results\reproduction_checked_20261024\scores\SPRT\MM2-MDP\manifest.json`

## SPRT/full/MM2-MDP/physical

依赖：SPRT/full/MM2-MDP/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method SPRT --router MM2-MDP --input results\reproduction_checked_20261024\routes\SPRT\MM2-MDP\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\SPRT\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\physical_scores\SPRT\MM2-MDP\results.csv`、`results\reproduction_checked_20261024\physical_scores\SPRT\MM2-MDP\input_binding.json`

## SPRT/full/MM2-MDP/road_tasks

依赖：SPRT/full/MM2-MDP/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method SPRT --router MM2-MDP --input results\reproduction_checked_20261024\routes\SPRT\MM2-MDP\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\SPRT\MM2-MDP\manifest.json --out results\reproduction_checked_20261024\road_tasks\SPRT\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\road_tasks\SPRT\MM2-MDP\metrics.json`、`results\reproduction_checked_20261024\road_tasks\SPRT\MM2-MDP\manifest.json`

## SPRT/train/M

依赖：冻结输入与公共资源

```powershell
.venv/Scripts/python.exe synthesize.py --config reproduction_checked_20261024/config.json --method SPRT --out results\reproduction_checked_20261024\measurements_train\SPRT --train-only
```

预期输出：`results\reproduction_checked_20261024\measurements_train\SPRT\measurement.pkl`、`results\reproduction_checked_20261024\measurements_train\SPRT\measurement_manifest.json`

## SPRT/train/Origin/R

依赖：SPRT/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method SPRT --router Origin --input results\reproduction_checked_20261024\measurements_train\SPRT --out results\reproduction_checked_20261024\routes_train\SPRT\Origin
```

预期输出：`results\reproduction_checked_20261024\routes_train\SPRT\Origin\synthetic_coordinates.pkl`、`results\reproduction_checked_20261024\routes_train\SPRT\Origin\route_manifest.json`

## SPRT/train/Nearest/R

依赖：SPRT/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method SPRT --router Nearest --input results\reproduction_checked_20261024\measurements_train\SPRT --out results\reproduction_checked_20261024\routes_train\SPRT\Nearest
```

预期输出：`results\reproduction_checked_20261024\routes_train\SPRT\Nearest\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\SPRT\Nearest\route_manifest.json`

## SPRT/train/FMM/R

依赖：SPRT/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method SPRT --router FMM --input results\reproduction_checked_20261024\measurements_train\SPRT --out results\reproduction_checked_20261024\routes_train\SPRT\FMM
```

预期输出：`results\reproduction_checked_20261024\routes_train\SPRT\FMM\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\SPRT\FMM\route_manifest.json`

## SPRT/train/STMatch/R

依赖：SPRT/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method SPRT --router STMatch --input results\reproduction_checked_20261024\measurements_train\SPRT --out results\reproduction_checked_20261024\routes_train\SPRT\STMatch
```

预期输出：`results\reproduction_checked_20261024\routes_train\SPRT\STMatch\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\SPRT\STMatch\route_manifest.json`

## SPRT/train/MM2-MDP/R

依赖：SPRT/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method SPRT --router MM2-MDP --input results\reproduction_checked_20261024\measurements_train\SPRT --out results\reproduction_checked_20261024\routes_train\SPRT\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\routes_train\SPRT\MM2-MDP\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\SPRT\MM2-MDP\route_manifest.json`

## PrivTrace/full/M

依赖：冻结输入与公共资源

```powershell
.venv/Scripts/python.exe synthesize.py --config reproduction_checked_20261024/config.json --method PrivTrace --out results\reproduction_checked_20261024\measurements\PrivTrace
```

预期输出：`results\reproduction_checked_20261024\measurements\PrivTrace\measurement.pkl`、`results\reproduction_checked_20261024\measurements\PrivTrace\measurement_manifest.json`

## PrivTrace/full/Origin/R

依赖：PrivTrace/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method PrivTrace --router Origin --input results\reproduction_checked_20261024\measurements\PrivTrace --out results\reproduction_checked_20261024\routes\PrivTrace\Origin
```

预期输出：`results\reproduction_checked_20261024\routes\PrivTrace\Origin\synthetic_coordinates.pkl`、`results\reproduction_checked_20261024\routes\PrivTrace\Origin\route_manifest.json`

## PrivTrace/full/Origin/coordinates

依赖：PrivTrace/full/Origin/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method PrivTrace --router Origin --input results\reproduction_checked_20261024\routes\PrivTrace\Origin\synthetic_coordinates.pkl --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\Origin
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\Origin\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\Origin\manifest.json`

## PrivTrace/full/Nearest/R

依赖：PrivTrace/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method PrivTrace --router Nearest --input results\reproduction_checked_20261024\measurements\PrivTrace --out results\reproduction_checked_20261024\routes\PrivTrace\Nearest
```

预期输出：`results\reproduction_checked_20261024\routes\PrivTrace\Nearest\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\PrivTrace\Nearest\route_manifest.json`

## PrivTrace/full/Nearest/coordinates

依赖：PrivTrace/full/Nearest/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method PrivTrace --router Nearest --input results\reproduction_checked_20261024\routes\PrivTrace\Nearest\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\Nearest
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\Nearest\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\Nearest\manifest.json`

## PrivTrace/full/Nearest/roads

依赖：PrivTrace/full/Nearest/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method PrivTrace --router Nearest --input results\reproduction_checked_20261024\routes\PrivTrace\Nearest\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\PrivTrace\Nearest
```

预期输出：`results\reproduction_checked_20261024\scores\PrivTrace\Nearest\metrics.json`、`results\reproduction_checked_20261024\scores\PrivTrace\Nearest\manifest.json`

## PrivTrace/full/Nearest/physical

依赖：PrivTrace/full/Nearest/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method PrivTrace --router Nearest --input results\reproduction_checked_20261024\routes\PrivTrace\Nearest\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\PrivTrace\Nearest
```

预期输出：`results\reproduction_checked_20261024\physical_scores\PrivTrace\Nearest\results.csv`、`results\reproduction_checked_20261024\physical_scores\PrivTrace\Nearest\input_binding.json`

## PrivTrace/full/Nearest/road_tasks

依赖：PrivTrace/full/Nearest/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method PrivTrace --router Nearest --input results\reproduction_checked_20261024\routes\PrivTrace\Nearest\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\PrivTrace\Nearest\manifest.json --out results\reproduction_checked_20261024\road_tasks\PrivTrace\Nearest
```

预期输出：`results\reproduction_checked_20261024\road_tasks\PrivTrace\Nearest\metrics.json`、`results\reproduction_checked_20261024\road_tasks\PrivTrace\Nearest\manifest.json`

## PrivTrace/full/FMM/R

依赖：PrivTrace/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method PrivTrace --router FMM --input results\reproduction_checked_20261024\measurements\PrivTrace --out results\reproduction_checked_20261024\routes\PrivTrace\FMM
```

预期输出：`results\reproduction_checked_20261024\routes\PrivTrace\FMM\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\PrivTrace\FMM\route_manifest.json`

## PrivTrace/full/FMM/coordinates

依赖：PrivTrace/full/FMM/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method PrivTrace --router FMM --input results\reproduction_checked_20261024\routes\PrivTrace\FMM\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\FMM
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\FMM\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\FMM\manifest.json`

## PrivTrace/full/FMM/roads

依赖：PrivTrace/full/FMM/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method PrivTrace --router FMM --input results\reproduction_checked_20261024\routes\PrivTrace\FMM\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\PrivTrace\FMM
```

预期输出：`results\reproduction_checked_20261024\scores\PrivTrace\FMM\metrics.json`、`results\reproduction_checked_20261024\scores\PrivTrace\FMM\manifest.json`

## PrivTrace/full/FMM/physical

依赖：PrivTrace/full/FMM/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method PrivTrace --router FMM --input results\reproduction_checked_20261024\routes\PrivTrace\FMM\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\PrivTrace\FMM
```

预期输出：`results\reproduction_checked_20261024\physical_scores\PrivTrace\FMM\results.csv`、`results\reproduction_checked_20261024\physical_scores\PrivTrace\FMM\input_binding.json`

## PrivTrace/full/FMM/road_tasks

依赖：PrivTrace/full/FMM/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method PrivTrace --router FMM --input results\reproduction_checked_20261024\routes\PrivTrace\FMM\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\PrivTrace\FMM\manifest.json --out results\reproduction_checked_20261024\road_tasks\PrivTrace\FMM
```

预期输出：`results\reproduction_checked_20261024\road_tasks\PrivTrace\FMM\metrics.json`、`results\reproduction_checked_20261024\road_tasks\PrivTrace\FMM\manifest.json`

## PrivTrace/full/STMatch/R

依赖：PrivTrace/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method PrivTrace --router STMatch --input results\reproduction_checked_20261024\measurements\PrivTrace --out results\reproduction_checked_20261024\routes\PrivTrace\STMatch
```

预期输出：`results\reproduction_checked_20261024\routes\PrivTrace\STMatch\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\PrivTrace\STMatch\route_manifest.json`

## PrivTrace/full/STMatch/coordinates

依赖：PrivTrace/full/STMatch/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method PrivTrace --router STMatch --input results\reproduction_checked_20261024\routes\PrivTrace\STMatch\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\STMatch
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\STMatch\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\STMatch\manifest.json`

## PrivTrace/full/STMatch/roads

依赖：PrivTrace/full/STMatch/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method PrivTrace --router STMatch --input results\reproduction_checked_20261024\routes\PrivTrace\STMatch\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\PrivTrace\STMatch
```

预期输出：`results\reproduction_checked_20261024\scores\PrivTrace\STMatch\metrics.json`、`results\reproduction_checked_20261024\scores\PrivTrace\STMatch\manifest.json`

## PrivTrace/full/STMatch/physical

依赖：PrivTrace/full/STMatch/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method PrivTrace --router STMatch --input results\reproduction_checked_20261024\routes\PrivTrace\STMatch\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\PrivTrace\STMatch
```

预期输出：`results\reproduction_checked_20261024\physical_scores\PrivTrace\STMatch\results.csv`、`results\reproduction_checked_20261024\physical_scores\PrivTrace\STMatch\input_binding.json`

## PrivTrace/full/STMatch/road_tasks

依赖：PrivTrace/full/STMatch/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method PrivTrace --router STMatch --input results\reproduction_checked_20261024\routes\PrivTrace\STMatch\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\PrivTrace\STMatch\manifest.json --out results\reproduction_checked_20261024\road_tasks\PrivTrace\STMatch
```

预期输出：`results\reproduction_checked_20261024\road_tasks\PrivTrace\STMatch\metrics.json`、`results\reproduction_checked_20261024\road_tasks\PrivTrace\STMatch\manifest.json`

## PrivTrace/full/MM2-MDP/R

依赖：PrivTrace/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method PrivTrace --router MM2-MDP --input results\reproduction_checked_20261024\measurements\PrivTrace --out results\reproduction_checked_20261024\routes\PrivTrace\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\routes\PrivTrace\MM2-MDP\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\PrivTrace\MM2-MDP\route_manifest.json`

## PrivTrace/full/MM2-MDP/coordinates

依赖：PrivTrace/full/MM2-MDP/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method PrivTrace --router MM2-MDP --input results\reproduction_checked_20261024\routes\PrivTrace\MM2-MDP\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\MM2-MDP\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\PrivTrace\MM2-MDP\manifest.json`

## PrivTrace/full/MM2-MDP/roads

依赖：PrivTrace/full/MM2-MDP/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method PrivTrace --router MM2-MDP --input results\reproduction_checked_20261024\routes\PrivTrace\MM2-MDP\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\PrivTrace\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\scores\PrivTrace\MM2-MDP\metrics.json`、`results\reproduction_checked_20261024\scores\PrivTrace\MM2-MDP\manifest.json`

## PrivTrace/full/MM2-MDP/physical

依赖：PrivTrace/full/MM2-MDP/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method PrivTrace --router MM2-MDP --input results\reproduction_checked_20261024\routes\PrivTrace\MM2-MDP\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\PrivTrace\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\physical_scores\PrivTrace\MM2-MDP\results.csv`、`results\reproduction_checked_20261024\physical_scores\PrivTrace\MM2-MDP\input_binding.json`

## PrivTrace/full/MM2-MDP/road_tasks

依赖：PrivTrace/full/MM2-MDP/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method PrivTrace --router MM2-MDP --input results\reproduction_checked_20261024\routes\PrivTrace\MM2-MDP\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\PrivTrace\MM2-MDP\manifest.json --out results\reproduction_checked_20261024\road_tasks\PrivTrace\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\road_tasks\PrivTrace\MM2-MDP\metrics.json`、`results\reproduction_checked_20261024\road_tasks\PrivTrace\MM2-MDP\manifest.json`

## PrivTrace/train/M

依赖：冻结输入与公共资源

```powershell
.venv/Scripts/python.exe synthesize.py --config reproduction_checked_20261024/config.json --method PrivTrace --out results\reproduction_checked_20261024\measurements_train\PrivTrace --train-only
```

预期输出：`results\reproduction_checked_20261024\measurements_train\PrivTrace\measurement.pkl`、`results\reproduction_checked_20261024\measurements_train\PrivTrace\measurement_manifest.json`

## PrivTrace/train/Origin/R

依赖：PrivTrace/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method PrivTrace --router Origin --input results\reproduction_checked_20261024\measurements_train\PrivTrace --out results\reproduction_checked_20261024\routes_train\PrivTrace\Origin
```

预期输出：`results\reproduction_checked_20261024\routes_train\PrivTrace\Origin\synthetic_coordinates.pkl`、`results\reproduction_checked_20261024\routes_train\PrivTrace\Origin\route_manifest.json`

## PrivTrace/train/Nearest/R

依赖：PrivTrace/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method PrivTrace --router Nearest --input results\reproduction_checked_20261024\measurements_train\PrivTrace --out results\reproduction_checked_20261024\routes_train\PrivTrace\Nearest
```

预期输出：`results\reproduction_checked_20261024\routes_train\PrivTrace\Nearest\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\PrivTrace\Nearest\route_manifest.json`

## PrivTrace/train/FMM/R

依赖：PrivTrace/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method PrivTrace --router FMM --input results\reproduction_checked_20261024\measurements_train\PrivTrace --out results\reproduction_checked_20261024\routes_train\PrivTrace\FMM
```

预期输出：`results\reproduction_checked_20261024\routes_train\PrivTrace\FMM\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\PrivTrace\FMM\route_manifest.json`

## PrivTrace/train/STMatch/R

依赖：PrivTrace/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method PrivTrace --router STMatch --input results\reproduction_checked_20261024\measurements_train\PrivTrace --out results\reproduction_checked_20261024\routes_train\PrivTrace\STMatch
```

预期输出：`results\reproduction_checked_20261024\routes_train\PrivTrace\STMatch\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\PrivTrace\STMatch\route_manifest.json`

## PrivTrace/train/MM2-MDP/R

依赖：PrivTrace/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method PrivTrace --router MM2-MDP --input results\reproduction_checked_20261024\measurements_train\PrivTrace --out results\reproduction_checked_20261024\routes_train\PrivTrace\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\routes_train\PrivTrace\MM2-MDP\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\PrivTrace\MM2-MDP\route_manifest.json`

## DPTraj-PM/full/M

依赖：冻结输入与公共资源

```powershell
.venv/Scripts/python.exe synthesize.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --out results\reproduction_checked_20261024\measurements\DPTraj-PM
```

预期输出：`results\reproduction_checked_20261024\measurements\DPTraj-PM\measurement.pkl`、`results\reproduction_checked_20261024\measurements\DPTraj-PM\measurement_manifest.json`

## DPTraj-PM/full/Origin/R

依赖：DPTraj-PM/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router Origin --input results\reproduction_checked_20261024\measurements\DPTraj-PM --out results\reproduction_checked_20261024\routes\DPTraj-PM\Origin
```

预期输出：`results\reproduction_checked_20261024\routes\DPTraj-PM\Origin\synthetic_coordinates.pkl`、`results\reproduction_checked_20261024\routes\DPTraj-PM\Origin\route_manifest.json`

## DPTraj-PM/full/Origin/coordinates

依赖：DPTraj-PM/full/Origin/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router Origin --input results\reproduction_checked_20261024\routes\DPTraj-PM\Origin\synthetic_coordinates.pkl --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\Origin
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\Origin\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\Origin\manifest.json`

## DPTraj-PM/full/Nearest/R

依赖：DPTraj-PM/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router Nearest --input results\reproduction_checked_20261024\measurements\DPTraj-PM --out results\reproduction_checked_20261024\routes\DPTraj-PM\Nearest
```

预期输出：`results\reproduction_checked_20261024\routes\DPTraj-PM\Nearest\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\DPTraj-PM\Nearest\route_manifest.json`

## DPTraj-PM/full/Nearest/coordinates

依赖：DPTraj-PM/full/Nearest/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router Nearest --input results\reproduction_checked_20261024\routes\DPTraj-PM\Nearest\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\Nearest
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\Nearest\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\Nearest\manifest.json`

## DPTraj-PM/full/Nearest/roads

依赖：DPTraj-PM/full/Nearest/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router Nearest --input results\reproduction_checked_20261024\routes\DPTraj-PM\Nearest\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\DPTraj-PM\Nearest
```

预期输出：`results\reproduction_checked_20261024\scores\DPTraj-PM\Nearest\metrics.json`、`results\reproduction_checked_20261024\scores\DPTraj-PM\Nearest\manifest.json`

## DPTraj-PM/full/Nearest/physical

依赖：DPTraj-PM/full/Nearest/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router Nearest --input results\reproduction_checked_20261024\routes\DPTraj-PM\Nearest\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\DPTraj-PM\Nearest
```

预期输出：`results\reproduction_checked_20261024\physical_scores\DPTraj-PM\Nearest\results.csv`、`results\reproduction_checked_20261024\physical_scores\DPTraj-PM\Nearest\input_binding.json`

## DPTraj-PM/full/Nearest/road_tasks

依赖：DPTraj-PM/full/Nearest/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router Nearest --input results\reproduction_checked_20261024\routes\DPTraj-PM\Nearest\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\DPTraj-PM\Nearest\manifest.json --out results\reproduction_checked_20261024\road_tasks\DPTraj-PM\Nearest
```

预期输出：`results\reproduction_checked_20261024\road_tasks\DPTraj-PM\Nearest\metrics.json`、`results\reproduction_checked_20261024\road_tasks\DPTraj-PM\Nearest\manifest.json`

## DPTraj-PM/full/FMM/R

依赖：DPTraj-PM/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router FMM --input results\reproduction_checked_20261024\measurements\DPTraj-PM --out results\reproduction_checked_20261024\routes\DPTraj-PM\FMM
```

预期输出：`results\reproduction_checked_20261024\routes\DPTraj-PM\FMM\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\DPTraj-PM\FMM\route_manifest.json`

## DPTraj-PM/full/FMM/coordinates

依赖：DPTraj-PM/full/FMM/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router FMM --input results\reproduction_checked_20261024\routes\DPTraj-PM\FMM\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\FMM
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\FMM\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\FMM\manifest.json`

## DPTraj-PM/full/FMM/roads

依赖：DPTraj-PM/full/FMM/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router FMM --input results\reproduction_checked_20261024\routes\DPTraj-PM\FMM\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\DPTraj-PM\FMM
```

预期输出：`results\reproduction_checked_20261024\scores\DPTraj-PM\FMM\metrics.json`、`results\reproduction_checked_20261024\scores\DPTraj-PM\FMM\manifest.json`

## DPTraj-PM/full/FMM/physical

依赖：DPTraj-PM/full/FMM/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router FMM --input results\reproduction_checked_20261024\routes\DPTraj-PM\FMM\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\DPTraj-PM\FMM
```

预期输出：`results\reproduction_checked_20261024\physical_scores\DPTraj-PM\FMM\results.csv`、`results\reproduction_checked_20261024\physical_scores\DPTraj-PM\FMM\input_binding.json`

## DPTraj-PM/full/FMM/road_tasks

依赖：DPTraj-PM/full/FMM/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router FMM --input results\reproduction_checked_20261024\routes\DPTraj-PM\FMM\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\DPTraj-PM\FMM\manifest.json --out results\reproduction_checked_20261024\road_tasks\DPTraj-PM\FMM
```

预期输出：`results\reproduction_checked_20261024\road_tasks\DPTraj-PM\FMM\metrics.json`、`results\reproduction_checked_20261024\road_tasks\DPTraj-PM\FMM\manifest.json`

## DPTraj-PM/full/STMatch/R

依赖：DPTraj-PM/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router STMatch --input results\reproduction_checked_20261024\measurements\DPTraj-PM --out results\reproduction_checked_20261024\routes\DPTraj-PM\STMatch
```

预期输出：`results\reproduction_checked_20261024\routes\DPTraj-PM\STMatch\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\DPTraj-PM\STMatch\route_manifest.json`

## DPTraj-PM/full/STMatch/coordinates

依赖：DPTraj-PM/full/STMatch/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router STMatch --input results\reproduction_checked_20261024\routes\DPTraj-PM\STMatch\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\STMatch
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\STMatch\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\STMatch\manifest.json`

## DPTraj-PM/full/STMatch/roads

依赖：DPTraj-PM/full/STMatch/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router STMatch --input results\reproduction_checked_20261024\routes\DPTraj-PM\STMatch\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\DPTraj-PM\STMatch
```

预期输出：`results\reproduction_checked_20261024\scores\DPTraj-PM\STMatch\metrics.json`、`results\reproduction_checked_20261024\scores\DPTraj-PM\STMatch\manifest.json`

## DPTraj-PM/full/STMatch/physical

依赖：DPTraj-PM/full/STMatch/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router STMatch --input results\reproduction_checked_20261024\routes\DPTraj-PM\STMatch\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\DPTraj-PM\STMatch
```

预期输出：`results\reproduction_checked_20261024\physical_scores\DPTraj-PM\STMatch\results.csv`、`results\reproduction_checked_20261024\physical_scores\DPTraj-PM\STMatch\input_binding.json`

## DPTraj-PM/full/STMatch/road_tasks

依赖：DPTraj-PM/full/STMatch/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router STMatch --input results\reproduction_checked_20261024\routes\DPTraj-PM\STMatch\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\DPTraj-PM\STMatch\manifest.json --out results\reproduction_checked_20261024\road_tasks\DPTraj-PM\STMatch
```

预期输出：`results\reproduction_checked_20261024\road_tasks\DPTraj-PM\STMatch\metrics.json`、`results\reproduction_checked_20261024\road_tasks\DPTraj-PM\STMatch\manifest.json`

## DPTraj-PM/full/MM2-MDP/R

依赖：DPTraj-PM/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router MM2-MDP --input results\reproduction_checked_20261024\measurements\DPTraj-PM --out results\reproduction_checked_20261024\routes\DPTraj-PM\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\routes\DPTraj-PM\MM2-MDP\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\DPTraj-PM\MM2-MDP\route_manifest.json`

## DPTraj-PM/full/MM2-MDP/coordinates

依赖：DPTraj-PM/full/MM2-MDP/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router MM2-MDP --input results\reproduction_checked_20261024\routes\DPTraj-PM\MM2-MDP\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\MM2-MDP\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPTraj-PM\MM2-MDP\manifest.json`

## DPTraj-PM/full/MM2-MDP/roads

依赖：DPTraj-PM/full/MM2-MDP/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router MM2-MDP --input results\reproduction_checked_20261024\routes\DPTraj-PM\MM2-MDP\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\DPTraj-PM\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\scores\DPTraj-PM\MM2-MDP\metrics.json`、`results\reproduction_checked_20261024\scores\DPTraj-PM\MM2-MDP\manifest.json`

## DPTraj-PM/full/MM2-MDP/physical

依赖：DPTraj-PM/full/MM2-MDP/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router MM2-MDP --input results\reproduction_checked_20261024\routes\DPTraj-PM\MM2-MDP\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\DPTraj-PM\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\physical_scores\DPTraj-PM\MM2-MDP\results.csv`、`results\reproduction_checked_20261024\physical_scores\DPTraj-PM\MM2-MDP\input_binding.json`

## DPTraj-PM/full/MM2-MDP/road_tasks

依赖：DPTraj-PM/full/MM2-MDP/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router MM2-MDP --input results\reproduction_checked_20261024\routes\DPTraj-PM\MM2-MDP\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\DPTraj-PM\MM2-MDP\manifest.json --out results\reproduction_checked_20261024\road_tasks\DPTraj-PM\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\road_tasks\DPTraj-PM\MM2-MDP\metrics.json`、`results\reproduction_checked_20261024\road_tasks\DPTraj-PM\MM2-MDP\manifest.json`

## DPTraj-PM/train/M

依赖：冻结输入与公共资源

```powershell
.venv/Scripts/python.exe synthesize.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --out results\reproduction_checked_20261024\measurements_train\DPTraj-PM --train-only
```

预期输出：`results\reproduction_checked_20261024\measurements_train\DPTraj-PM\measurement.pkl`、`results\reproduction_checked_20261024\measurements_train\DPTraj-PM\measurement_manifest.json`

## DPTraj-PM/train/Origin/R

依赖：DPTraj-PM/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router Origin --input results\reproduction_checked_20261024\measurements_train\DPTraj-PM --out results\reproduction_checked_20261024\routes_train\DPTraj-PM\Origin
```

预期输出：`results\reproduction_checked_20261024\routes_train\DPTraj-PM\Origin\synthetic_coordinates.pkl`、`results\reproduction_checked_20261024\routes_train\DPTraj-PM\Origin\route_manifest.json`

## DPTraj-PM/train/Nearest/R

依赖：DPTraj-PM/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router Nearest --input results\reproduction_checked_20261024\measurements_train\DPTraj-PM --out results\reproduction_checked_20261024\routes_train\DPTraj-PM\Nearest
```

预期输出：`results\reproduction_checked_20261024\routes_train\DPTraj-PM\Nearest\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\DPTraj-PM\Nearest\route_manifest.json`

## DPTraj-PM/train/FMM/R

依赖：DPTraj-PM/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router FMM --input results\reproduction_checked_20261024\measurements_train\DPTraj-PM --out results\reproduction_checked_20261024\routes_train\DPTraj-PM\FMM
```

预期输出：`results\reproduction_checked_20261024\routes_train\DPTraj-PM\FMM\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\DPTraj-PM\FMM\route_manifest.json`

## DPTraj-PM/train/STMatch/R

依赖：DPTraj-PM/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router STMatch --input results\reproduction_checked_20261024\measurements_train\DPTraj-PM --out results\reproduction_checked_20261024\routes_train\DPTraj-PM\STMatch
```

预期输出：`results\reproduction_checked_20261024\routes_train\DPTraj-PM\STMatch\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\DPTraj-PM\STMatch\route_manifest.json`

## DPTraj-PM/train/MM2-MDP/R

依赖：DPTraj-PM/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPTraj-PM --router MM2-MDP --input results\reproduction_checked_20261024\measurements_train\DPTraj-PM --out results\reproduction_checked_20261024\routes_train\DPTraj-PM\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\routes_train\DPTraj-PM\MM2-MDP\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\DPTraj-PM\MM2-MDP\route_manifest.json`

## DPStd/full/M

依赖：冻结输入与公共资源

```powershell
.venv/Scripts/python.exe synthesize.py --config reproduction_checked_20261024/config.json --method DPStd --out results\reproduction_checked_20261024\measurements\DPStd
```

预期输出：`results\reproduction_checked_20261024\measurements\DPStd\measurement.pkl`、`results\reproduction_checked_20261024\measurements\DPStd\measurement_manifest.json`

## DPStd/full/Origin/R

依赖：DPStd/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPStd --router Origin --input results\reproduction_checked_20261024\measurements\DPStd --out results\reproduction_checked_20261024\routes\DPStd\Origin
```

预期输出：`results\reproduction_checked_20261024\routes\DPStd\Origin\synthetic_coordinates.pkl`、`results\reproduction_checked_20261024\routes\DPStd\Origin\route_manifest.json`

## DPStd/full/Origin/coordinates

依赖：DPStd/full/Origin/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method DPStd --router Origin --input results\reproduction_checked_20261024\routes\DPStd\Origin\synthetic_coordinates.pkl --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\Origin
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\Origin\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\Origin\manifest.json`

## DPStd/full/Nearest/R

依赖：DPStd/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPStd --router Nearest --input results\reproduction_checked_20261024\measurements\DPStd --out results\reproduction_checked_20261024\routes\DPStd\Nearest
```

预期输出：`results\reproduction_checked_20261024\routes\DPStd\Nearest\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\DPStd\Nearest\route_manifest.json`

## DPStd/full/Nearest/coordinates

依赖：DPStd/full/Nearest/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method DPStd --router Nearest --input results\reproduction_checked_20261024\routes\DPStd\Nearest\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\Nearest
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\Nearest\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\Nearest\manifest.json`

## DPStd/full/Nearest/roads

依赖：DPStd/full/Nearest/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method DPStd --router Nearest --input results\reproduction_checked_20261024\routes\DPStd\Nearest\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\DPStd\Nearest
```

预期输出：`results\reproduction_checked_20261024\scores\DPStd\Nearest\metrics.json`、`results\reproduction_checked_20261024\scores\DPStd\Nearest\manifest.json`

## DPStd/full/Nearest/physical

依赖：DPStd/full/Nearest/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method DPStd --router Nearest --input results\reproduction_checked_20261024\routes\DPStd\Nearest\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\DPStd\Nearest
```

预期输出：`results\reproduction_checked_20261024\physical_scores\DPStd\Nearest\results.csv`、`results\reproduction_checked_20261024\physical_scores\DPStd\Nearest\input_binding.json`

## DPStd/full/Nearest/road_tasks

依赖：DPStd/full/Nearest/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method DPStd --router Nearest --input results\reproduction_checked_20261024\routes\DPStd\Nearest\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\DPStd\Nearest\manifest.json --out results\reproduction_checked_20261024\road_tasks\DPStd\Nearest
```

预期输出：`results\reproduction_checked_20261024\road_tasks\DPStd\Nearest\metrics.json`、`results\reproduction_checked_20261024\road_tasks\DPStd\Nearest\manifest.json`

## DPStd/full/FMM/R

依赖：DPStd/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPStd --router FMM --input results\reproduction_checked_20261024\measurements\DPStd --out results\reproduction_checked_20261024\routes\DPStd\FMM
```

预期输出：`results\reproduction_checked_20261024\routes\DPStd\FMM\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\DPStd\FMM\route_manifest.json`

## DPStd/full/FMM/coordinates

依赖：DPStd/full/FMM/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method DPStd --router FMM --input results\reproduction_checked_20261024\routes\DPStd\FMM\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\FMM
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\FMM\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\FMM\manifest.json`

## DPStd/full/FMM/roads

依赖：DPStd/full/FMM/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method DPStd --router FMM --input results\reproduction_checked_20261024\routes\DPStd\FMM\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\DPStd\FMM
```

预期输出：`results\reproduction_checked_20261024\scores\DPStd\FMM\metrics.json`、`results\reproduction_checked_20261024\scores\DPStd\FMM\manifest.json`

## DPStd/full/FMM/physical

依赖：DPStd/full/FMM/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method DPStd --router FMM --input results\reproduction_checked_20261024\routes\DPStd\FMM\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\DPStd\FMM
```

预期输出：`results\reproduction_checked_20261024\physical_scores\DPStd\FMM\results.csv`、`results\reproduction_checked_20261024\physical_scores\DPStd\FMM\input_binding.json`

## DPStd/full/FMM/road_tasks

依赖：DPStd/full/FMM/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method DPStd --router FMM --input results\reproduction_checked_20261024\routes\DPStd\FMM\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\DPStd\FMM\manifest.json --out results\reproduction_checked_20261024\road_tasks\DPStd\FMM
```

预期输出：`results\reproduction_checked_20261024\road_tasks\DPStd\FMM\metrics.json`、`results\reproduction_checked_20261024\road_tasks\DPStd\FMM\manifest.json`

## DPStd/full/STMatch/R

依赖：DPStd/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPStd --router STMatch --input results\reproduction_checked_20261024\measurements\DPStd --out results\reproduction_checked_20261024\routes\DPStd\STMatch
```

预期输出：`results\reproduction_checked_20261024\routes\DPStd\STMatch\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\DPStd\STMatch\route_manifest.json`

## DPStd/full/STMatch/coordinates

依赖：DPStd/full/STMatch/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method DPStd --router STMatch --input results\reproduction_checked_20261024\routes\DPStd\STMatch\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\STMatch
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\STMatch\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\STMatch\manifest.json`

## DPStd/full/STMatch/roads

依赖：DPStd/full/STMatch/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method DPStd --router STMatch --input results\reproduction_checked_20261024\routes\DPStd\STMatch\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\DPStd\STMatch
```

预期输出：`results\reproduction_checked_20261024\scores\DPStd\STMatch\metrics.json`、`results\reproduction_checked_20261024\scores\DPStd\STMatch\manifest.json`

## DPStd/full/STMatch/physical

依赖：DPStd/full/STMatch/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method DPStd --router STMatch --input results\reproduction_checked_20261024\routes\DPStd\STMatch\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\DPStd\STMatch
```

预期输出：`results\reproduction_checked_20261024\physical_scores\DPStd\STMatch\results.csv`、`results\reproduction_checked_20261024\physical_scores\DPStd\STMatch\input_binding.json`

## DPStd/full/STMatch/road_tasks

依赖：DPStd/full/STMatch/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method DPStd --router STMatch --input results\reproduction_checked_20261024\routes\DPStd\STMatch\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\DPStd\STMatch\manifest.json --out results\reproduction_checked_20261024\road_tasks\DPStd\STMatch
```

预期输出：`results\reproduction_checked_20261024\road_tasks\DPStd\STMatch\metrics.json`、`results\reproduction_checked_20261024\road_tasks\DPStd\STMatch\manifest.json`

## DPStd/full/MM2-MDP/R

依赖：DPStd/full/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPStd --router MM2-MDP --input results\reproduction_checked_20261024\measurements\DPStd --out results\reproduction_checked_20261024\routes\DPStd\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\routes\DPStd\MM2-MDP\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes\DPStd\MM2-MDP\route_manifest.json`

## DPStd/full/MM2-MDP/coordinates

依赖：DPStd/full/MM2-MDP/R

```powershell
.venv/Scripts/python.exe evaluate_coordinates.py --config reproduction_checked_20261024/config.json --method DPStd --router MM2-MDP --input results\reproduction_checked_20261024\routes\DPStd\MM2-MDP\synthetic_routes.pkl.gz --metric-protocol audit-v2 --out results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\MM2-MDP\metrics.json`、`results\reproduction_checked_20261024\coordinate_scores_audit_v2\DPStd\MM2-MDP\manifest.json`

## DPStd/full/MM2-MDP/roads

依赖：DPStd/full/MM2-MDP/R

```powershell
.venv/Scripts/python.exe evaluate.py --config reproduction_checked_20261024/config.json --method DPStd --router MM2-MDP --input results\reproduction_checked_20261024\routes\DPStd\MM2-MDP\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\scores\DPStd\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\scores\DPStd\MM2-MDP\metrics.json`、`results\reproduction_checked_20261024\scores\DPStd\MM2-MDP\manifest.json`

## DPStd/full/MM2-MDP/physical

依赖：DPStd/full/MM2-MDP/R

```powershell
.venv/Scripts/python.exe evaluate_physical.py --config reproduction_checked_20261024/config.json --method DPStd --router MM2-MDP --input results\reproduction_checked_20261024\routes\DPStd\MM2-MDP\synthetic_routes.pkl.gz --out results\reproduction_checked_20261024\physical_scores\DPStd\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\physical_scores\DPStd\MM2-MDP\results.csv`、`results\reproduction_checked_20261024\physical_scores\DPStd\MM2-MDP\input_binding.json`

## DPStd/full/MM2-MDP/road_tasks

依赖：DPStd/full/MM2-MDP/roads

```powershell
.venv/Scripts/python.exe evaluate_road_tasks.py --config reproduction_checked_20261024/config.json --method DPStd --router MM2-MDP --input results\reproduction_checked_20261024\routes\DPStd\MM2-MDP\synthetic_routes.pkl.gz --score-manifest results\reproduction_checked_20261024\scores\DPStd\MM2-MDP\manifest.json --out results\reproduction_checked_20261024\road_tasks\DPStd\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\road_tasks\DPStd\MM2-MDP\metrics.json`、`results\reproduction_checked_20261024\road_tasks\DPStd\MM2-MDP\manifest.json`

## DPStd/train/M

依赖：冻结输入与公共资源

```powershell
.venv/Scripts/python.exe synthesize.py --config reproduction_checked_20261024/config.json --method DPStd --out results\reproduction_checked_20261024\measurements_train\DPStd --train-only
```

预期输出：`results\reproduction_checked_20261024\measurements_train\DPStd\measurement.pkl`、`results\reproduction_checked_20261024\measurements_train\DPStd\measurement_manifest.json`

## DPStd/train/Origin/R

依赖：DPStd/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPStd --router Origin --input results\reproduction_checked_20261024\measurements_train\DPStd --out results\reproduction_checked_20261024\routes_train\DPStd\Origin
```

预期输出：`results\reproduction_checked_20261024\routes_train\DPStd\Origin\synthetic_coordinates.pkl`、`results\reproduction_checked_20261024\routes_train\DPStd\Origin\route_manifest.json`

## DPStd/train/Nearest/R

依赖：DPStd/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPStd --router Nearest --input results\reproduction_checked_20261024\measurements_train\DPStd --out results\reproduction_checked_20261024\routes_train\DPStd\Nearest
```

预期输出：`results\reproduction_checked_20261024\routes_train\DPStd\Nearest\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\DPStd\Nearest\route_manifest.json`

## DPStd/train/FMM/R

依赖：DPStd/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPStd --router FMM --input results\reproduction_checked_20261024\measurements_train\DPStd --out results\reproduction_checked_20261024\routes_train\DPStd\FMM
```

预期输出：`results\reproduction_checked_20261024\routes_train\DPStd\FMM\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\DPStd\FMM\route_manifest.json`

## DPStd/train/STMatch/R

依赖：DPStd/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPStd --router STMatch --input results\reproduction_checked_20261024\measurements_train\DPStd --out results\reproduction_checked_20261024\routes_train\DPStd\STMatch
```

预期输出：`results\reproduction_checked_20261024\routes_train\DPStd\STMatch\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\DPStd\STMatch\route_manifest.json`

## DPStd/train/MM2-MDP/R

依赖：DPStd/train/M

```powershell
.venv/Scripts/python.exe route.py --config reproduction_checked_20261024/config.json --method DPStd --router MM2-MDP --input results\reproduction_checked_20261024\measurements_train\DPStd --out results\reproduction_checked_20261024\routes_train\DPStd\MM2-MDP
```

预期输出：`results\reproduction_checked_20261024\routes_train\DPStd\MM2-MDP\synthetic_routes.pkl.gz`、`results\reproduction_checked_20261024\routes_train\DPStd\MM2-MDP\route_manifest.json`

