# 第03-2节 DPMM与MTNet生成

[完整运行指南](../README_CN.md#sec-03-2) · [上一节：03-1](第03-1节_DFR全集与训练专用生成.md) · [下一节：04](第04节_原生方法全集效用评分.md)

所有命令均在仓库的 `reproduction/beijing` 工作目录执行；文档位于仓库根目录，不要因为打开了分节文件就切换工作目录。北京默认，Porto只在第01节首次处理数据前选择一次配置。完整指南与分节版内容相同，选择一种阅读执行，不要两份都跑。

命令中的文件名和目录名沿用当前北京示例。`--config` 是配置，`--input` 是上游产物，`--out` 是新输出目录；自行改名时同步修改后续引用。每条命令成功并核对产物后再继续，已有成功产物按记录接续，不从头重复生成。

个别命令的 `--document` 指向仓库原命令文件，供执行来源登记使用；这些文件保留，无需跳过去阅读或再次执行。

本节有两条独立流程：DPMM先核对加速一致性再生成；MTNet先整理输入、导出训练目录，再训练和原生生成。MTNet输入准备成功不等于训练完成。两种方法的输出都保留自身原生形式。


在交付目录执行。下面为新批次命令；已生成的正式结果不重跑。DPMM、MTNet各是完整原生方法，不展开为多个R，也不再次匹配。

## DPMM

先核对当前输入的验证记录。仅有历史数据的证据不能替代本批验证；当前输入已有完整60条通过记录时直接复用，不重复慢速验证。否则分别执行：

**步骤 03-2.01：对当前DPMM输入核对原版与加速版是否一致。**

读取：--split选的真实输入、公共图和两份源码。

```powershell
.venv/Scripts/python.exe validate_dpmm_dataset.py --config configs/experiments/configs/beijing.json --adapter vendor/dpmm/original/check/run_dpmm_official_beijing.py --optimizer vendor/dpmm/fast_dpmm_paths.py --out results/reproduction_native_20261024/validation/full --records 60 --exact-records 60 --split full
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--adapter` | 原作者DPMM运行适配程序的路径，用于验证或调用原算法。 |
| `--optimizer` | 已实现的DPMM路径加速程序，需先完成与原版的一致性验证。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |
| `--records` | DPMM对照验证要检查的输入记录数量；本例60。 |
| `--exact-records` | 明确指定本轮完整对照的记录数；本例60，全部通过后才继续生成。 |
| `--split` | 选择DPMM的数据范围：full为全集，train为训练集。 |

完成后：validation.json；指定的60条全部比较通过后再生成。

**步骤 03-2.02：对当前DPMM输入核对原版与加速版是否一致。**

读取：--split选的真实输入、公共图和两份源码。

```powershell
.venv/Scripts/python.exe validate_dpmm_dataset.py --config configs/experiments/configs/beijing.json --adapter vendor/dpmm/original/check/run_dpmm_official_beijing.py --optimizer vendor/dpmm/fast_dpmm_paths.py --out results/reproduction_native_20261024/validation/train --records 60 --exact-records 60 --split train
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--adapter` | 原作者DPMM运行适配程序的路径，用于验证或调用原算法。 |
| `--optimizer` | 已实现的DPMM路径加速程序，需先完成与原版的一致性验证。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |
| `--records` | DPMM对照验证要检查的输入记录数量；本例60。 |
| `--exact-records` | 明确指定本轮完整对照的记录数；本例60，全部通过后才继续生成。 |
| `--split` | 选择DPMM的数据范围：full为全集，train为训练集。 |

完成后：validation.json；指定的60条全部比较通过后再生成。

全量与train分别绑定已有加速验证。两个预算均请求1.4；其隐私单位与DFR不同，不能据此声称隐私定义等价。

**步骤 03-2.03：用已经通过验证的DPMM加速实现生成数据。**

读取：--split选的真实输入和对应验证报告。

```powershell
.venv/Scripts/python.exe synthesize_dpmm.py --config configs/experiments/configs/beijing.json --adapter vendor/dpmm/original/check/run_dpmm_official_beijing.py --optimizer vendor/dpmm/fast_dpmm_paths.py --validation results/reproduction_native_20261024/validation/full/validation.json --workers 2 --split full --out results/reproduction_native_20261024/full/DPMM
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--adapter` | 原作者DPMM运行适配程序的路径，用于验证或调用原算法。 |
| `--optimizer` | 已实现的DPMM路径加速程序，需先完成与原版的一致性验证。 |
| `--validation` | 本批输入、道路图和源码对应的验证结果JSON；不是任意旧报告。 |
| `--workers` | 同时运行的计算进程数；不是CPU线程数，也不是输出轨迹数。 |
| `--split` | 选择DPMM的数据范围：full为全集，train为训练集。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：dpmm.pkl、dpmm.json和new_dataset_execution.json。

生成 results/reproduction_native_20261024/full/DPMM/dpmm.pkl、dpmm.json、new_dataset_execution.json。workers仅改变已验证的并行执行，不改变记录算法。

训练专用DPMM在生成前登记文档原句，生成后立即记录该命令的真实退出码。登记器不执行或替换生成命令，不把内部子进程冒充外层命令；这是操作者记录，不是操作系统证明。下面三条按顺序在同一PowerShell窗口执行，生成失败也执行最后的记录命令保存失败。

**步骤 03-2.04：登记DPMM生成前后的原命令、耗时和退出码。**

读取：仓库原命令文档及本次生成目录。

```powershell
.venv/Scripts/python.exe tools/record_native_execution.py start --document REPRODUCE_NATIVE_BASELINES_20261024_CN.md --output results/reproduction_native_20261024/train/DPMM --ledger results/reproduction_native_20261024/train/dpmm_execution.jsonl
```

| 参数 | 简单含义 |
|---|---|
| `--document` | 用于登记实际生成命令来源的仓库命令文件；保留原路径，不是另一个待执行步骤。 |
| `--output` | 执行登记器所跟踪的生成目录；必须与对应生成命令的 --out 相同。 |
| `--ledger` | 保存开始、结束、实际退出码和耗时的执行账本文件。 |

完成后：追加执行账本；start只登记开始，finish核对实际退出，不代替生成。

**步骤 03-2.05：用已经通过验证的DPMM加速实现生成数据。**

读取：--split选的真实输入和对应验证报告。

```powershell
.venv/Scripts/python.exe synthesize_dpmm.py --config configs/experiments/configs/beijing.json --adapter vendor/dpmm/original/check/run_dpmm_official_beijing.py --optimizer vendor/dpmm/fast_dpmm_paths.py --validation results/reproduction_native_20261024/validation/train/validation.json --workers 3 --split train --validation-protocol slow-equivalence --out results/reproduction_native_20261024/train/DPMM
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--adapter` | 原作者DPMM运行适配程序的路径，用于验证或调用原算法。 |
| `--optimizer` | 已实现的DPMM路径加速程序，需先完成与原版的一致性验证。 |
| `--validation` | 本批输入、道路图和源码对应的验证结果JSON；不是任意旧报告。 |
| `--workers` | 同时运行的计算进程数；不是CPU线程数，也不是输出轨迹数。 |
| `--split` | 选择DPMM的数据范围：full为全集，train为训练集。 |
| `--validation-protocol` | 声明使用哪种验证证据；slow-equivalence要求原版与加速版输出一致。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：dpmm.pkl、dpmm.json和new_dataset_execution.json。

**步骤 03-2.06：登记DPMM生成前后的原命令、耗时和退出码。**

读取：仓库原命令文档及本次生成目录。

```powershell
.venv/Scripts/python.exe tools/record_native_execution.py finish --document REPRODUCE_NATIVE_BASELINES_20261024_CN.md --output results/reproduction_native_20261024/train/DPMM --ledger results/reproduction_native_20261024/train/dpmm_execution.jsonl --exit-code $LASTEXITCODE
```

| 参数 | 简单含义 |
|---|---|
| `--document` | 用于登记实际生成命令来源的仓库命令文件；保留原路径，不是另一个待执行步骤。 |
| `--output` | 执行登记器所跟踪的生成目录；必须与对应生成命令的 --out 相同。 |
| `--ledger` | 保存开始、结束、实际退出码和耗时的执行账本文件。 |
| `--exit-code` | 记录刚完成命令的实际退出码；$LASTEXITCODE应立即读取，0表示成功。 |

完成后：追加执行账本；start只登记开始，finish核对实际退出，不代替生成。

生成 results/reproduction_native_20261024/train/DPMM/dpmm.pkl、dpmm.json、new_dataset_execution.json。workers仅改变已验证的并行执行，不改变记录算法。

## MTNet

先准备作者格式，再导出冻结训练目录；全量与训练分开。训练需NVIDIA CUDA环境，不以CPU静默替代；使用 deployment/SETUP_MTNET_GPU.ps1 的已锁定环境。作者长度筛选后的可训练数与输出槽位数不同，manifest分别记录，不将筛选后的训练覆盖声称为全集覆盖。

**步骤 03-2.07：将当前道路与起止时间整理成MTNet作者输入格式。**

读取：配置中的道路数据和来源时间；--train-only只取训练集。

```powershell
.venv/Scripts/python.exe prepare_mtnet_frozen.py --config configs/experiments/configs/beijing.json --original-adapter-root vendor/mtnet --out results/reproduction_native_20261024/full/MTNet_prepared
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--original-adapter-root` | 保存MTNet作者格式转换代码的目录。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |

完成后：MTNet输入目录及full_preparation_manifest.json；作者长度过滤后的可训练数另列。

生成 results/reproduction_native_20261024/full/MTNet_prepared/full_preparation_manifest.json 及 data/beijing_roads_l20。

**步骤 03-2.08：导出可以训练的MTNet独立目录。**

读取：上一条准备结果和作者代码。

```powershell
.venv/Scripts/python.exe prepare_mtnet_deployment.py --prepared results/reproduction_native_20261024/full/MTNet_prepared --original-root vendor/mtnet --out results/reproduction_native_20261024/full/MTNet_deployment --archive results/reproduction_native_20261024/full/MTNet_deployment.zip
```

| 参数 | 简单含义 |
|---|---|
| `--prepared` | 上一条MTNet格式准备命令写出的目录。 |
| `--original-root` | MTNet作者程序所在目录，供导出训练目录时复制和核对源码。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |
| `--archive` | 把导出的MTNet目录再打包成这个ZIP文件；这是输出，不是待下载数据。 |

完成后：MTNet_deployment目录及ZIP；此时还没有训练模型。

生成带源码锁、公共输出数量和数据划分绑定的 results/reproduction_native_20261024/full/MTNet_deployment。

**步骤 03-2.09：训练MTNet并执行作者原生生成。**

读取：-Root指向的导出训练目录及指定Python。

```powershell
powershell -NoProfile -File deployment/RUN_MTNET_GPU.ps1 -Root results/reproduction_native_20261024/full/MTNet_deployment -PythonExecutable .venv/Scripts/python.exe
```

| 参数 | 简单含义 |
|---|---|
| `-NoProfile` | 启动PowerShell时不加载个人启动脚本，减少个人设置干扰。 |
| `-File` | 接下来给出要运行的PowerShell脚本文件。 |
| `-Root` | GPU安装或训练脚本处理的根目录；训练时指向对应MTNet_deployment。 |
| `-PythonExecutable` | 实际训练使用的Python程序；本例指定项目虚拟环境中的解释器。 |

完成后：trained模型、native_release、独立标准输出/错误日志及真实退出记录。

生成 results/reproduction_native_20261024/full/MTNet_deployment/trained 与 native_release，stdout/stderr分别保存；已有trained目录会拒绝重复训练。

**步骤 03-2.10：将当前道路与起止时间整理成MTNet作者输入格式。**

读取：配置中的道路数据和来源时间；--train-only只取训练集。

```powershell
.venv/Scripts/python.exe prepare_mtnet_frozen.py --config configs/experiments/configs/beijing.json --original-adapter-root vendor/mtnet --out results/reproduction_native_20261024/train/MTNet_prepared --train-only
```

| 参数 | 简单含义 |
|---|---|
| `--config` | 读取这一份实验配置：真实数据、道路图、分集和算法设置从这里取得。 |
| `--original-adapter-root` | 保存MTNet作者格式转换代码的目录。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |
| `--train-only` | 只把真实训练集交给生成器，保留真实测试集供后续检验。 |

完成后：MTNet输入目录及full_preparation_manifest.json；作者长度过滤后的可训练数另列。

生成 results/reproduction_native_20261024/train/MTNet_prepared/full_preparation_manifest.json 及 data/beijing_roads_l20。

**步骤 03-2.11：导出可以训练的MTNet独立目录。**

读取：上一条准备结果和作者代码。

```powershell
.venv/Scripts/python.exe prepare_mtnet_deployment.py --prepared results/reproduction_native_20261024/train/MTNet_prepared --original-root vendor/mtnet --out results/reproduction_native_20261024/train/MTNet_deployment --archive results/reproduction_native_20261024/train/MTNet_deployment.zip --train-only
```

| 参数 | 简单含义 |
|---|---|
| `--prepared` | 上一条MTNet格式准备命令写出的目录。 |
| `--original-root` | MTNet作者程序所在目录，供导出训练目录时复制和核对源码。 |
| `--out` | 本次输出的位置；改名后，后续读取这个结果的路径也要一起改。 |
| `--archive` | 把导出的MTNet目录再打包成这个ZIP文件；这是输出，不是待下载数据。 |
| `--train-only` | 只把真实训练集交给生成器，保留真实测试集供后续检验。 |

完成后：MTNet_deployment目录及ZIP；此时还没有训练模型。

生成带源码锁、公共输出数量和数据划分绑定的 results/reproduction_native_20261024/train/MTNet_deployment。

**步骤 03-2.12：训练MTNet并执行作者原生生成。**

读取：-Root指向的导出训练目录及指定Python。

```powershell
powershell -NoProfile -File deployment/RUN_MTNET_GPU.ps1 -Root results/reproduction_native_20261024/train/MTNet_deployment -PythonExecutable .venv/Scripts/python.exe
```

| 参数 | 简单含义 |
|---|---|
| `-NoProfile` | 启动PowerShell时不加载个人启动脚本，减少个人设置干扰。 |
| `-File` | 接下来给出要运行的PowerShell脚本文件。 |
| `-Root` | GPU安装或训练脚本处理的根目录；训练时指向对应MTNet_deployment。 |
| `-PythonExecutable` | 实际训练使用的Python程序；本例指定项目虚拟环境中的解释器。 |

完成后：trained模型、native_release、独立标准输出/错误日志及真实退出记录。

生成 results/reproduction_native_20261024/train/MTNet_deployment/trained 与 native_release，stdout/stderr分别保存；已有trained目录会拒绝重复训练。

训练和原生生成成功后还写出execution_observation.json，保存真实子进程退出码及耗时，不伪造外层命令。之后按 [新原生结果的TSTR接续](第05-2节_原生方法严格TSTR.md) 登记、转换和评分。

---

[完整运行指南](../README_CN.md#sec-03-2) · [上一节：03-1](第03-1节_DFR全集与训练专用生成.md) · [下一节：04](第04节_原生方法全集效用评分.md)
