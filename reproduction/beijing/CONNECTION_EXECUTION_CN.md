# 三处接续修复：本轮独立检查命令

本机、交付根目录执行。仅检查改变的接口与旧结果算术，不重新训练或生成正式实验。fixture为小型程序测试，不计为算法成绩。

```powershell
.venv/Scripts/python.exe -m pytest tests/test_portable_connections.py -q -p no:cacheprovider
```

新增接续说明的真实参数解析；不执行长任务：

```powershell
.venv/Scripts/python.exe tools/audit_readme_commands.py --supplement REPRODUCE_NATIVE_TSTR_CN.md --supplement REPRODUCE_NEW_MATRIX_CN.md --out validation/connection_commands_20261024.json
```

复用两份实际保存评分，只测试新多目录收集入口，不重评分：

```powershell
.venv/Scripts/python.exe tools/prepare_matrix_connection_check.py
```

```powershell
.venv/Scripts/python.exe tools/collect_frozen_matrix.py --batch validation/connection_cli/stat --batch validation/connection_cli/native --spec reference_results/matrix/spec.json --out validation/connection_cli/matrix
```

```powershell
.venv/Scripts/python.exe tools/verify_matrix_connection_check.py
```

仅新增K收集器文件链测试，使用标为fixture的小文件，不是生成新的科研成绩：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_k_collector_connection.py -q -p no:cacheprovider
```
