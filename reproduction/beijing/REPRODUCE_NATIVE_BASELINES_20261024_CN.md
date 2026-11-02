# 原生基线：生成入口

按仓库根 README 第8步准备配置，并在同一 PowerShell 窗口执行本页。本页随仓库提供，不由运行命令生成。`configs/experiments/` 是当前数据的配置目录；`results/` 下的名称以北京复现为例，不是必须的文件名。更改结果目录时，将本页及依赖文档中对应的 `--out`、`--input`、`--source` 等路径同步替换；不要改算法名、预算或种子来代替改文件名。Porto 使用另一个检出目录，命令相同。

在交付目录执行。下面为新批次命令；已生成的正式结果不重跑。DPMM、MTNet各是完整原生方法，不展开为多个R，也不再次匹配。

## DPMM

先核对当前输入的验证记录。仅有历史数据的证据不能替代本批验证；当前输入已有完整60条通过记录时直接复用，不重复慢速验证。否则分别执行：

```powershell
.venv/Scripts/python.exe validate_dpmm_dataset.py --config configs/experiments/configs/beijing.json --adapter vendor/dpmm/original/check/run_dpmm_official_beijing.py --optimizer vendor/dpmm/fast_dpmm_paths.py --out results/reproduction_native_20261024/validation/full --records 60 --exact-records 60 --split full
.venv/Scripts/python.exe validate_dpmm_dataset.py --config configs/experiments/configs/beijing.json --adapter vendor/dpmm/original/check/run_dpmm_official_beijing.py --optimizer vendor/dpmm/fast_dpmm_paths.py --out results/reproduction_native_20261024/validation/train --records 60 --exact-records 60 --split train
```

全量与train分别绑定已有加速验证。两个预算均请求1.4；其隐私单位与DFR不同，不能据此声称隐私定义等价。

```powershell
.venv/Scripts/python.exe synthesize_dpmm.py --config configs/experiments/configs/beijing.json --adapter vendor/dpmm/original/check/run_dpmm_official_beijing.py --optimizer vendor/dpmm/fast_dpmm_paths.py --validation results/reproduction_native_20261024/validation/full/validation.json --workers 2 --split full --out results/reproduction_native_20261024/full/DPMM
```

生成 results/reproduction_native_20261024/full/DPMM/dpmm.pkl、dpmm.json、new_dataset_execution.json。workers仅改变已验证的并行执行，不改变记录算法。

训练专用DPMM在生成前登记文档原句，生成后立即记录该命令的真实退出码。登记器不执行或替换生成命令，不把内部子进程冒充外层命令；这是操作者记录，不是操作系统证明。下面三条按顺序在同一PowerShell窗口执行，生成失败也执行最后的记录命令保存失败。

```powershell
.venv/Scripts/python.exe tools/record_native_execution.py start --document REPRODUCE_NATIVE_BASELINES_20261024_CN.md --output results/reproduction_native_20261024/train/DPMM --ledger results/reproduction_native_20261024/train/dpmm_execution.jsonl
```

```powershell
.venv/Scripts/python.exe synthesize_dpmm.py --config configs/experiments/configs/beijing.json --adapter vendor/dpmm/original/check/run_dpmm_official_beijing.py --optimizer vendor/dpmm/fast_dpmm_paths.py --validation results/reproduction_native_20261024/validation/train/validation.json --workers 3 --split train --validation-protocol slow-equivalence --out results/reproduction_native_20261024/train/DPMM
```

```powershell
.venv/Scripts/python.exe tools/record_native_execution.py finish --document REPRODUCE_NATIVE_BASELINES_20261024_CN.md --output results/reproduction_native_20261024/train/DPMM --ledger results/reproduction_native_20261024/train/dpmm_execution.jsonl --exit-code $LASTEXITCODE
```

生成 results/reproduction_native_20261024/train/DPMM/dpmm.pkl、dpmm.json、new_dataset_execution.json。workers仅改变已验证的并行执行，不改变记录算法。

## MTNet

先准备作者格式，再导出冻结训练目录；全量与训练分开。训练需NVIDIA CUDA环境，不以CPU静默替代；使用 deployment/SETUP_MTNET_GPU.ps1 的已锁定环境。作者长度筛选后的可训练数与输出槽位数不同，manifest分别记录，不将筛选后的训练覆盖声称为全集覆盖。

```powershell
.venv/Scripts/python.exe prepare_mtnet_frozen.py --config configs/experiments/configs/beijing.json --original-adapter-root vendor/mtnet --out results/reproduction_native_20261024/full/MTNet_prepared
```

生成 results/reproduction_native_20261024/full/MTNet_prepared/full_preparation_manifest.json 及 data/beijing_roads_l20。

```powershell
.venv/Scripts/python.exe prepare_mtnet_deployment.py --prepared results/reproduction_native_20261024/full/MTNet_prepared --original-root vendor/mtnet --out results/reproduction_native_20261024/full/MTNet_deployment --archive results/reproduction_native_20261024/full/MTNet_deployment.zip
```

生成带源码锁、公共输出数量和数据划分绑定的 results/reproduction_native_20261024/full/MTNet_deployment。

```powershell
powershell -NoProfile -File deployment/RUN_MTNET_GPU.ps1 -Root results/reproduction_native_20261024/full/MTNet_deployment -PythonExecutable .venv/Scripts/python.exe
```

生成 results/reproduction_native_20261024/full/MTNet_deployment/trained 与 native_release，stdout/stderr分别保存；已有trained目录会拒绝重复训练。

```powershell
.venv/Scripts/python.exe prepare_mtnet_frozen.py --config configs/experiments/configs/beijing.json --original-adapter-root vendor/mtnet --out results/reproduction_native_20261024/train/MTNet_prepared --train-only
```

生成 results/reproduction_native_20261024/train/MTNet_prepared/full_preparation_manifest.json 及 data/beijing_roads_l20。

```powershell
.venv/Scripts/python.exe prepare_mtnet_deployment.py --prepared results/reproduction_native_20261024/train/MTNet_prepared --original-root vendor/mtnet --out results/reproduction_native_20261024/train/MTNet_deployment --archive results/reproduction_native_20261024/train/MTNet_deployment.zip --train-only
```

生成带源码锁、公共输出数量和数据划分绑定的 results/reproduction_native_20261024/train/MTNet_deployment。

```powershell
powershell -NoProfile -File deployment/RUN_MTNET_GPU.ps1 -Root results/reproduction_native_20261024/train/MTNet_deployment -PythonExecutable .venv/Scripts/python.exe
```

生成 results/reproduction_native_20261024/train/MTNet_deployment/trained 与 native_release，stdout/stderr分别保存；已有trained目录会拒绝重复训练。

训练和原生生成成功后还写出execution_observation.json，保存真实子进程退出码及耗时，不伪造外层命令。之后按 [新原生结果的TSTR接续](REPRODUCE_NATIVE_TSTR_CN.md) 登记、转换和评分。
