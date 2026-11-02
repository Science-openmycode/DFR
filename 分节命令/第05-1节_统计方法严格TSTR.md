# 第05-1节 统计方法严格TSTR

[完整运行指南](../README_CN.md#sec-05-1) · [上一节：04](第04节_原生方法全集效用评分.md) · [下一节：05-2](第05-2节_原生方法严格TSTR.md)

所有命令均在仓库的 `reproduction/beijing` 工作目录执行；文档位于仓库根目录，不要因为打开了分节文件就切换工作目录。北京默认，Porto只在第01节首次处理数据前选择一次配置。完整指南与分节版内容相同，选择一种阅读执行，不要两份都跑。

命令中的文件名和目录名沿用当前北京示例。`--config` 是配置，`--input` 是上游产物，`--out` 是新输出目录；自行改名时同步修改后续引用。每条命令成功并核对产物后再继续，已有成功产物按记录接续，不从头重复生成。

个别命令的 `--document` 指向仓库原命令文件，供执行来源登记使用；这些文件保留，无需跳过去阅读或再次执行。

TSTR的意思是：用合成数据训练任务模型，用真实测试数据检验。这里读取第02节的训练专用发布；真实训练集不能包含测试记录，各算法使用同一真实测试集。


工作目录为交付根目录。先完成 reproduction_checked_20261024/COMMANDS_CN.md 中的训练 M 与训练 R。下面只转换已有道路的确定几何，再训练下游模型并在同一真实测试集评分；不会重新合成或重新匹配。

四个 M 的 lineage.json 来自实际训练专用生成，不能用全集发布的 lineage 代替。坐标视图保留全部输出槽位，包括空槽位。指标协议固定 audit-v2。

这些是新批次执行说明，不表示本轮重跑了正式 TSTR。已有冻结成绩继续保留。

## SPRT + Origin


**步骤 05-1.01：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method SPRT --router Origin --input results/reproduction_checked_20261024/measurements_train/SPRT/measurement.pkl --lineage results/reproduction_checked_20261024/measurements_train/SPRT/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/SPRT/Origin
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/SPRT/Origin/results.csv 和 manifest.json。

## SPRT + Nearest

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.02：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/SPRT/Nearest/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/SPRT/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/SPRT/Nearest
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/SPRT/Nearest/coordinates.pkl 及其来源 manifest。

**步骤 05-1.03：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method SPRT --router Nearest --input results/reproduction_checked_20261024/coordinate_views_train/SPRT/Nearest/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/SPRT/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/SPRT/Nearest
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/SPRT/Nearest/results.csv 和 manifest.json。

## SPRT + FMM

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.04：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/SPRT/FMM/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/SPRT/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/SPRT/FMM
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/SPRT/FMM/coordinates.pkl 及其来源 manifest。

**步骤 05-1.05：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method SPRT --router FMM --input results/reproduction_checked_20261024/coordinate_views_train/SPRT/FMM/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/SPRT/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/SPRT/FMM
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/SPRT/FMM/results.csv 和 manifest.json。

## SPRT + STMatch

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.06：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/SPRT/STMatch/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/SPRT/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/SPRT/STMatch
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/SPRT/STMatch/coordinates.pkl 及其来源 manifest。

**步骤 05-1.07：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method SPRT --router STMatch --input results/reproduction_checked_20261024/coordinate_views_train/SPRT/STMatch/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/SPRT/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/SPRT/STMatch
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/SPRT/STMatch/results.csv 和 manifest.json。

## SPRT + MM2-MDP

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.08：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/SPRT/MM2-MDP/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/SPRT/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/SPRT/MM2-MDP
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/SPRT/MM2-MDP/coordinates.pkl 及其来源 manifest。

**步骤 05-1.09：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method SPRT --router MM2-MDP --input results/reproduction_checked_20261024/coordinate_views_train/SPRT/MM2-MDP/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/SPRT/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/SPRT/MM2-MDP
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/SPRT/MM2-MDP/results.csv 和 manifest.json。

## PrivTrace + Origin


**步骤 05-1.10：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method PrivTrace --router Origin --input results/reproduction_checked_20261024/measurements_train/PrivTrace/measurement.pkl --lineage results/reproduction_checked_20261024/measurements_train/PrivTrace/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/Origin
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/Origin/results.csv 和 manifest.json。

## PrivTrace + Nearest

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.11：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/PrivTrace/Nearest/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/PrivTrace/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/Nearest
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/Nearest/coordinates.pkl 及其来源 manifest。

**步骤 05-1.12：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method PrivTrace --router Nearest --input results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/Nearest/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/PrivTrace/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/Nearest
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/Nearest/results.csv 和 manifest.json。

## PrivTrace + FMM

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.13：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/PrivTrace/FMM/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/PrivTrace/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/FMM
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/FMM/coordinates.pkl 及其来源 manifest。

**步骤 05-1.14：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method PrivTrace --router FMM --input results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/FMM/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/PrivTrace/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/FMM
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/FMM/results.csv 和 manifest.json。

## PrivTrace + STMatch

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.15：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/PrivTrace/STMatch/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/PrivTrace/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/STMatch
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/STMatch/coordinates.pkl 及其来源 manifest。

**步骤 05-1.16：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method PrivTrace --router STMatch --input results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/STMatch/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/PrivTrace/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/STMatch
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/STMatch/results.csv 和 manifest.json。

## PrivTrace + MM2-MDP

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.17：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/PrivTrace/MM2-MDP/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/PrivTrace/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/MM2-MDP
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/MM2-MDP/coordinates.pkl 及其来源 manifest。

**步骤 05-1.18：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method PrivTrace --router MM2-MDP --input results/reproduction_checked_20261024/coordinate_views_train/PrivTrace/MM2-MDP/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/PrivTrace/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/MM2-MDP
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/PrivTrace/MM2-MDP/results.csv 和 manifest.json。

## DPTraj-PM + Origin


**步骤 05-1.19：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method DPTraj-PM --router Origin --input results/reproduction_checked_20261024/measurements_train/DPTraj-PM/measurement.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPTraj-PM/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/Origin
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/Origin/results.csv 和 manifest.json。

## DPTraj-PM + Nearest

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.20：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPTraj-PM/Nearest/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPTraj-PM/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/Nearest
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/Nearest/coordinates.pkl 及其来源 manifest。

**步骤 05-1.21：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method DPTraj-PM --router Nearest --input results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/Nearest/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPTraj-PM/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/Nearest
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/Nearest/results.csv 和 manifest.json。

## DPTraj-PM + FMM

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.22：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPTraj-PM/FMM/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPTraj-PM/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/FMM
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/FMM/coordinates.pkl 及其来源 manifest。

**步骤 05-1.23：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method DPTraj-PM --router FMM --input results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/FMM/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPTraj-PM/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/FMM
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/FMM/results.csv 和 manifest.json。

## DPTraj-PM + STMatch

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.24：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPTraj-PM/STMatch/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPTraj-PM/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/STMatch
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/STMatch/coordinates.pkl 及其来源 manifest。

**步骤 05-1.25：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method DPTraj-PM --router STMatch --input results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/STMatch/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPTraj-PM/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/STMatch
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/STMatch/results.csv 和 manifest.json。

## DPTraj-PM + MM2-MDP

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.26：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPTraj-PM/MM2-MDP/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPTraj-PM/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/MM2-MDP
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/MM2-MDP/coordinates.pkl 及其来源 manifest。

**步骤 05-1.27：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method DPTraj-PM --router MM2-MDP --input results/reproduction_checked_20261024/coordinate_views_train/DPTraj-PM/MM2-MDP/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPTraj-PM/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/MM2-MDP
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPTraj-PM/MM2-MDP/results.csv 和 manifest.json。

## DPStd + Origin


**步骤 05-1.28：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method DPStd --router Origin --input results/reproduction_checked_20261024/measurements_train/DPStd/measurement.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPStd/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPStd/Origin
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPStd/Origin/results.csv 和 manifest.json。

## DPStd + Nearest

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.29：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPStd/Nearest/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPStd/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPStd/Nearest
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/DPStd/Nearest/coordinates.pkl 及其来源 manifest。

**步骤 05-1.30：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method DPStd --router Nearest --input results/reproduction_checked_20261024/coordinate_views_train/DPStd/Nearest/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPStd/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPStd/Nearest
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPStd/Nearest/results.csv 和 manifest.json。

## DPStd + FMM

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.31：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPStd/FMM/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPStd/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPStd/FMM
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/DPStd/FMM/coordinates.pkl 及其来源 manifest。

**步骤 05-1.32：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method DPStd --router FMM --input results/reproduction_checked_20261024/coordinate_views_train/DPStd/FMM/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPStd/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPStd/FMM
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPStd/FMM/results.csv 和 manifest.json。

## DPStd + STMatch

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.33：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPStd/STMatch/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPStd/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPStd/STMatch
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/DPStd/STMatch/coordinates.pkl 及其来源 manifest。

**步骤 05-1.34：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method DPStd --router STMatch --input results/reproduction_checked_20261024/coordinate_views_train/DPStd/STMatch/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPStd/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPStd/STMatch
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPStd/STMatch/results.csv 和 manifest.json。

## DPStd + MM2-MDP

先将已有道路编号转为确定几何，不添加道路：

**步骤 05-1.35：为统计方法的训练专用道路结果准备坐标表示。**

读取：同一训练发布的道路和measurement.pkl。

```powershell
.venv/Scripts/python.exe tools/stage_bound_coordinates.py --config configs/experiments/reproduction_checked_20261024/config.json --routes results/reproduction_checked_20261024/routes_train/DPStd/MM2-MDP/synthetic_routes.pkl.gz --measurement results/reproduction_checked_20261024/measurements_train/DPStd/measurement.pkl --out results/reproduction_checked_20261024/coordinate_views_train/DPStd/MM2-MDP
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--measurement` | 与道路结果对应的本次M输出坐标文件，帮助保持槽位及来源一致；不是原始真实轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：对应坐标文件及训练来源，供下一条TSTR读取。

生成：results/reproduction_checked_20261024/coordinate_views_train/DPStd/MM2-MDP/coordinates.pkl 及其来源 manifest。

**步骤 05-1.36：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/reproduction_checked_20261024/config.json --method DPStd --router MM2-MDP --input results/reproduction_checked_20261024/coordinate_views_train/DPStd/MM2-MDP/coordinates.pkl --lineage results/reproduction_checked_20261024/measurements_train/DPStd/lineage.json --metric-protocol audit-v2 --out results/reproduction_checked_20261024/tstr_audit_v2/DPStd/MM2-MDP
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--router` | 标记这份已保存结果对应的道路方法；这里是评分，不再次运行该路由。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

生成：results/reproduction_checked_20261024/tstr_audit_v2/DPStd/MM2-MDP/results.csv 和 manifest.json。

---

[完整运行指南](../README_CN.md#sec-05-1) · [上一节：04](第04节_原生方法全集效用评分.md) · [下一节：05-2](第05-2节_原生方法严格TSTR.md)
