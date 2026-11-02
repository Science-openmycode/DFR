# 正式 DFR：与既有矩阵一致的长度恢复分支

按仓库根 README 第8步准备配置，并在同一 PowerShell 窗口执行本页。本页随仓库提供，不由运行命令生成。`configs/experiments/` 是当前数据的配置目录；`results/` 下的名称以北京复现为例，不是必须的文件名。更改结果目录时，将本页及依赖文档中对应的 `--out`、`--input`、`--source` 等路径同步替换；不要改算法名、预算或种子来代替改文件名。Porto 使用另一个检出目录，命令相同。

既有正式 input_lineage.json 明确 length_aware=true、epsilon=1.4、seed=42。因此正式重现必须带 --length-aware；REPRODUCE_NATIVE_20261024_CN.md 中不带该参数的基础分支误启动记录保留，不用于正式图。工作目录为复制后的本交付目录，不要求服务器D盘位置。环境 PYTHONUTF8=1、PYTHONIOENCODING=utf-8。

## 全集15730条

```powershell
.venv/Scripts/python.exe synthesize_dfr.py --config configs/experiments/configs/beijing.json --length-aware --out results/reproduction_dfr_length_20261024/native/MTR-DFR
```

预期原生发布 results/reproduction_dfr_length_20261024/native/MTR-DFR/seed_42_length/road_routes.pkl.gz；私有来源记录为同级 MTR-DFR.private_audit/input_lineage.json。长度查询在总epsilon=1.4内按原算法比例分配，不额外提高总预算。

## 训练专用12584条

```powershell
.venv/Scripts/python.exe synthesize_dfr_train.py --config configs/experiments/configs/beijing.json --length-aware --out results/reproduction_dfr_length_20261024/native_train/MTR-DFR
```

预期原生发布 results/reproduction_dfr_length_20261024/native_train/MTR-DFR/release/seed_42_length/road_routes.pkl.gz，训练来源记录 native_train/MTR-DFR/lineage.json。生成后必须核对槽位、源码、输入、epsilon和length_aware分支，不能仅凭文件存在宣称复现。
