# 原生基线：生成入口

在交付目录执行。下面为新批次命令；已生成的正式结果不重跑。DPMM、MTNet各是完整原生方法，不展开为多个R，也不再次匹配。

## DPMM

全量与train分别绑定已有加速验证。两个预算均请求1.4；其隐私单位与DFR不同，不能据此声称隐私定义等价。

```powershell
.venv/Scripts/python.exe synthesize_dpmm.py --config configs/beijing.json --adapter vendor/dpmm/original/check/run_dpmm_official_beijing.py --optimizer vendor/dpmm/fast_dpmm_paths.py --validation vendor/dpmm/evidence/full_equivalence.json --workers 2 --split full --out results/reproduction_native_20261024/full/DPMM
```

生成 results/reproduction_native_20261024/full/DPMM/dpmm.pkl、dpmm.json、new_dataset_execution.json。workers仅改变已验证的并行执行，不改变记录算法。

训练专用DPMM在生成前登记文档原句，生成后立即记录该命令的真实退出码。登记器不执行或替换生成命令，不把内部子进程冒充外层命令；这是操作者记录，不是操作系统证明。下面三条按顺序在同一PowerShell窗口执行，生成失败也执行最后的记录命令保存失败。

```powershell
.venv/Scripts/python.exe tools/record_native_execution.py start --document REPRODUCE_NATIVE_BASELINES_20261024_CN.md --output results/reproduction_native_20261024/train/DPMM --ledger results/reproduction_native_20261024/train/dpmm_execution.jsonl
```

```powershell
.venv/Scripts/python.exe synthesize_dpmm.py --config configs/beijing.json --adapter vendor/dpmm/original/check/run_dpmm_official_beijing.py --optimizer vendor/dpmm/fast_dpmm_paths.py --validation vendor/dpmm/evidence/train_accelerated.json --workers 3 --split train --validation-protocol accelerated-only --out results/reproduction_native_20261024/train/DPMM
```

```powershell
.venv/Scripts/python.exe tools/record_native_execution.py finish --document REPRODUCE_NATIVE_BASELINES_20261024_CN.md --output results/reproduction_native_20261024/train/DPMM --ledger results/reproduction_native_20261024/train/dpmm_execution.jsonl --exit-code $LASTEXITCODE
```

生成 results/reproduction_native_20261024/train/DPMM/dpmm.pkl、dpmm.json、new_dataset_execution.json。workers仅改变已验证的并行执行，不改变记录算法。

## MTNet

先准备作者格式，再导出冻结训练目录；全量与训练分开。训练需NVIDIA CUDA环境，不以CPU静默替代；使用 deployment/SETUP_MTNET_GPU.ps1 的已锁定环境。作者长度筛选后的可训练数与输出槽位数不同，manifest分别记录，不将筛选后的训练覆盖声称为全集覆盖。

```powershell
.venv/Scripts/python.exe prepare_mtnet_frozen.py --config configs/beijing.json --original-adapter-root vendor/mtnet --time-binding resources/mtnet/time_binding.json --raw-reference resources/mtnet/original_timestamp_reference.pkl --out results/reproduction_native_20261024/full/MTNet_prepared
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
.venv/Scripts/python.exe prepare_mtnet_frozen.py --config configs/beijing.json --original-adapter-root vendor/mtnet --time-binding resources/mtnet/time_binding.json --raw-reference resources/mtnet/original_timestamp_reference.pkl --out results/reproduction_native_20261024/train/MTNet_prepared --train-only
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
