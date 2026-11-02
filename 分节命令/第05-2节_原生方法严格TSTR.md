# 第05-2节 原生方法严格TSTR

[完整运行指南](../README_CN.md#sec-05-2) · [上一节：05-1](第05-1节_统计方法严格TSTR.md) · [下一节：06](第06节_算法消融与隐私攻击.md)

所有命令均在仓库的 `reproduction/beijing` 工作目录执行；文档位于仓库根目录，不要因为打开了分节文件就切换工作目录。北京默认，Porto只在第01节首次处理数据前选择一次配置。完整指南与分节版内容相同，选择一种阅读执行，不要两份都跑。

命令中的文件名和目录名沿用当前北京示例。`--config` 是配置，`--input` 是上游产物，`--out` 是新输出目录；自行改名时同步修改后续引用。每条命令成功并核对产物后再继续，已有成功产物按记录接续，不从头重复生成。

个别命令的 `--document` 指向仓库原命令文件，供执行来源登记使用；这些文件保留，无需跳过去阅读或再次执行。

与上一节的问题相同，但输入换成DFR、DPMM、MTNet的训练专用原生发布。先核对实际训练来源，再做需要的道路/坐标表示转换，最后训练并评价下游任务模型。


先按DFR生成说明或原生基线说明完成训练专用发布。以下读取新批次，不读取保存的旧分数，不重新训练生成器。所有路径相对本目录；输出已存在时停止，保留旧结果。每个评分命令在合成训练集训练任务模型，在同一3146条真实测试集测试。

## 1. DPMM

上一节DPMM的start、生成、finish三个命令完成后，验证实际退出记录、12584条训练输入和已验证加速器，恢复缺失输出槽位为空，不填造轨迹：

**步骤 05-2.01：核对DPMM训练专用生成记录并准备评价坐标。**

读取：训练发布、真实退出账本及训练范围验证报告。

```powershell
.venv/Scripts/python.exe tools/prepare_dpmm_train_evaluation.py --directory results/reproduction_native_20261024/train/DPMM --config configs/experiments/configs/beijing.json --ledger results/reproduction_native_20261024/train/dpmm_execution.jsonl --document REPRODUCE_NATIVE_BASELINES_20261024_CN.md --validation results/reproduction_native_20261024/validation/train/validation.json --out results/reproduction_native_20261024/train/DPMM_view
```

| 参数 | 简单含义 |
|---|---|
| `--directory` | 已经完成的原生生成或模型目录，供登记与核对读取。 |
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--ledger` | 保存开始、结束、实际退出码和耗时的执行账本文件。 |
| `--document` | 用于登记实际生成命令来源的仓库命令文件；保留原路径，不是另一个待执行步骤。 |
| `--validation` | 本批输入、道路图和源码对应的验证结果JSON；不是任意旧报告。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：DPMM_view中的coordinates.pkl、manifest.json和lineage.json。

输出coordinates.pkl、manifest.json、lineage.json。随后评分：

**步骤 05-2.02：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/configs/beijing.json --method DPMM --input results/reproduction_native_20261024/train/DPMM_view/coordinates.pkl --lineage results/reproduction_native_20261024/train/DPMM_view/lineage.json --metric-protocol audit-v2 --out results/reproduction_native_20261024/tstr_audit_v2/DPMM/Origin
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

## 2. MTNet

RUN_MTNET_GPU.ps1已保存训练和生成子进程退出码；以下同时检查30轮训练日志、训练划分、模型和原生发布：

**步骤 05-2.03：补齐并核对MTNet训练专用发布的实际来源。**

读取：已训练目录、输入准备清单和当前配置。

```powershell
.venv/Scripts/python.exe tools/finalize_mtnet_lineage.py --directory results/reproduction_native_20261024/train/MTNet_deployment --preparation results/reproduction_native_20261024/train/MTNet_prepared/full_preparation_manifest.json --config configs/experiments/configs/beijing.json
```

| 参数 | 简单含义 |
|---|---|
| `--directory` | 已经完成的原生生成或模型目录，供登记与核对读取。 |
| `--preparation` | MTNet输入准备阶段的清单文件，用来核对人数、数据范围和来源。 |
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |

完成后：训练来源记录；不重新训练或生成。

输出部署目录内lineage.json。再登记原生道路ID，不做匹配：

**步骤 05-2.04：把训练完成后的MTNet原生输出登记成公共道路记录。**

读取：native_release、准备清单及真实训练模型。

```powershell
.venv/Scripts/python.exe register_mtnet.py --config configs/experiments/configs/beijing.json --source results/reproduction_native_20261024/train/MTNet_deployment/native_release --train-only --preparation results/reproduction_native_20261024/train/MTNet_prepared/full_preparation_manifest.json --model results/reproduction_native_20261024/train/MTNet_deployment/trained/model.pt --out results/reproduction_native_20261024/train/MTNet_routes
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--source` | 输入来源路径；登记MTNet时是native_release目录，预算作图时是summary.json。 |
| `--train-only` | 只把真实训练集交给生成器，保留真实测试集供后续检验。 |
| `--preparation` | MTNet输入准备阶段的清单文件，用来核对人数、数据范围和来源。 |
| `--model` | 实际训练得到的模型文件；不是准备输入时生成的文件。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：MTNet_routes中的道路文件及来源清单；不重新匹配。

转换公共边的确定几何，保留槽位和原生来源绑定：

**步骤 05-2.05：从既有原生道路取得确定的道路几何坐标。**

读取：登记后的道路、同城图、缓存和原生来源。

```powershell
.venv/Scripts/python.exe tools/stage_native_saved_coordinates.py --routes results/reproduction_native_20261024/train/MTNet_routes/synthetic_routes.pkl.gz --network "$Network" --edge-cache "$EdgeCache" --native-source results/reproduction_native_20261024/train/MTNet_deployment/native_release/routes.pkl --for-tstr --out-dir results/reproduction_native_20261024/train/MTNet_view
```

| 参数 | 简单含义 |
|---|---|
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--network` | 所选城市的公共道路图文件；不是合成轨迹。 |
| `--edge-cache` | 道路几何或道路评价缓存；选择本条命令对应城市的文件。 |
| `--native-source` | 转换前的原生道路发布文件，保留转换前后来源对应关系。 |
| `--for-tstr` | 这份表示转换用于训练专用TSTR；要求保留训练来源，不能混入全集模型。 |
| `--out-dir` | 本次输出目录；不要指向需要保留的旧结果。 |

完成后：coordinates.pkl和来源记录；不补路、不选新路线。

**步骤 05-2.06：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/configs/beijing.json --method MTNet --input results/reproduction_native_20261024/train/MTNet_view/coordinates.pkl --lineage results/reproduction_native_20261024/train/MTNet_deployment/lineage.json --metric-protocol audit-v2 --out results/reproduction_native_20261024/tstr_audit_v2/MTNet/Origin
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

## 3. MTR-DFR

原生节点对只转换为同一公共边的ID，不重新路由：

**步骤 05-2.07：将原生节点对表示转换为相同道路的编号。**

读取：原生道路文件、所选城市图及明确的源编号缓存。

```powershell
.venv/Scripts/python.exe tools/convert_native_node_pairs.py --routes results/reproduction_dfr_length_20261024/native_train/MTR-DFR/release/seed_42_length/road_routes.pkl.gz --source-cache "$MetricCache" --network "$Network" --expected-slots $TrainSlots --out results/reproduction_dfr_length_20261024/train_routes/MTR-DFR
```

| 参数 | 简单含义 |
|---|---|
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--source-cache` | 说明原生节点编号含义的缓存，通过共同道路编号与评价路网对应。 |
| `--network` | 所选城市的公共道路图文件；不是合成轨迹。 |
| `--expected-slots` | 应有的输出槽位总数；空槽也算在内，不能只数成功轨迹。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：synthetic_routes.pkl.gz及转换清单，空槽保留。

**步骤 05-2.08：从既有原生道路取得确定的道路几何坐标。**

读取：登记后的道路、同城图、缓存和原生来源。

```powershell
.venv/Scripts/python.exe tools/stage_native_saved_coordinates.py --routes results/reproduction_dfr_length_20261024/train_routes/MTR-DFR/synthetic_routes.pkl.gz --network "$Network" --edge-cache "$EdgeCache" --native-source results/reproduction_dfr_length_20261024/native_train/MTR-DFR/release/seed_42_length/road_routes.pkl.gz --for-tstr --out-dir results/reproduction_dfr_length_20261024/train_view/MTR-DFR
```

| 参数 | 简单含义 |
|---|---|
| `--routes` | 已经生成的道路轨迹文件，用于表示转换或坐标准备。 |
| `--network` | 所选城市的公共道路图文件；不是合成轨迹。 |
| `--edge-cache` | 道路几何或道路评价缓存；选择本条命令对应城市的文件。 |
| `--native-source` | 转换前的原生道路发布文件，保留转换前后来源对应关系。 |
| `--for-tstr` | 这份表示转换用于训练专用TSTR；要求保留训练来源，不能混入全集模型。 |
| `--out-dir` | 本次输出目录；不要指向需要保留的旧结果。 |

完成后：coordinates.pkl和来源记录；不补路、不选新路线。

**步骤 05-2.09：检验合成训练数据替代真实训练数据的能力。**

读取：合成训练专用坐标及来源；测试始终用固定真实测试集。

```powershell
.venv/Scripts/python.exe evaluate_tstr.py --config configs/experiments/configs/beijing.json --method MTR-DFR --input results/reproduction_dfr_length_20261024/train_view/MTR-DFR/coordinates.pkl --lineage results/reproduction_dfr_length_20261024/native_train/MTR-DFR/lineage.json --metric-protocol audit-v2 --out results/reproduction_dfr_length_20261024/tstr_audit_v2/MTR-DFR/Origin
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--method` | 标记本次要处理或评价的方法；评分命令只读已有发布，不会因此重新生成。 |
| `--input` | 本条命令读取的上游产物；应是前面已成功生成的文件或目录。 |
| `--lineage` | 实际训练专用生成的来源记录；用它确认没有拿全集模型替代训练模型。 |
| `--metric-protocol` | 评分规则版本；本指南用audit-v2，各方法保持相同版本。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：results.csv和manifest.json；这里训练的是下游任务模型，不重训轨迹生成器。

三个方法各输出results.csv和manifest.json。结果中的Real-train使用同一真实训练/测试划分；严格TSTR不与全集回顾性道路预测混为一项。

---

[完整运行指南](../README_CN.md#sec-05-2) · [上一节：05-1](第05-1节_统计方法严格TSTR.md) · [下一节：06](第06节_算法消融与隐私攻击.md)
