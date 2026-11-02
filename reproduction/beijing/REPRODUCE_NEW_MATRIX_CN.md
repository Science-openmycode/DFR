# 新评分 → 新矩阵 → 同版式图

按仓库根 README 第8步准备配置，并在同一 PowerShell 窗口执行本页。本页随仓库提供，不由运行命令生成。`configs/experiments/` 是当前数据的配置目录；`results/` 下的名称以北京复现为例，不是必须的文件名。更改结果目录时，将本页及依赖文档中对应的 `--out`、`--input`、`--source` 等路径同步替换；不要改算法名、预算或种子来代替改文件名。Porto 使用另一个检出目录，命令相同。

前置：统计M×R、DFR、原生基线和严格TSTR命令分别完成相应评分。下面只收集各新结果目录，不计算分数、不读旧CSV填数、不重复算法。一个目录没有某项时保留MISSING；重复格子分数冲突则停止。原生方法各一行，不把输出再匹配到多个R。

```powershell
.venv/Scripts/python.exe tools/collect_frozen_matrix.py --config configs/experiments/configs/beijing.json --batch results/reproduction_checked_20261024 --batch results/reproduction_native_20261024 --batch results/reproduction_dfr_length_20261024 --spec reference_results/matrix/spec.json --out results/reproduction_matrix/sources
```

输出matrix_sources.csv与manifest.json。每格记录真实评分JSON/CSV、对应manifest和来源指标；统计和严格TSTR分别保留scope。1215格是27×45的展示位置，不表示每格都有成绩。

```powershell
.venv/Scripts/python.exe plotting/render_verified_matrix.py --sources results/reproduction_matrix/sources --previous reference_results/matrix_previous --spec reference_results/matrix/spec.json --new-batch --out results/reproduction_matrix/figures
```

输出current_full.png/PDF、各分组图、逐图旧版/新版对照、cells.json以及manifest.json。使用同一绘图函数、行列和配色；新结果允许与旧结果不同，每个变化记录before/after，而不强迫新随机批次逐值相等。没有新评分的格子不会从旧图补数。

仅重画旧冻结结果时仍用SUPPLEMENT_COMMANDS_CN.md中的命令，不加--new-batch；旧模式仍逐值检查不变。
