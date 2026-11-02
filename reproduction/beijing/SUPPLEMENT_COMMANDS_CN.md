# 补充实验：当前数据的独立命令

按仓库根 README 第8步准备配置，并在同一 PowerShell 窗口执行本页。本页随仓库提供，不由运行命令生成。`configs/experiments/` 是当前数据的配置目录；`results/` 下的名称以北京复现为例，不是必须的文件名。更改结果目录时，将本页及依赖文档中对应的 `--out`、`--input`、`--source` 等路径同步替换；不要改算法名、预算或种子来代替改文件名。Porto 使用另一个检出目录，命令相同。

先完成各生成、评分及训练专用发布；四项道路应用见仓库主README第05节。攻击准备检查本批23份训练发布，不读取旧北京成绩。K、预算与端点诊断先执行 supplement/sweeps 内对应的逐条命令，再执行本页汇总。

## 1. 算法级消融

```powershell
.venv/Scripts/python.exe run_dfr_ablation_frozen.py --config configs/experiments/configs/beijing.json --out results/ablation/ablation
```

## 2. 消融作图

```powershell
.venv/Scripts/python.exe tools/plot_executed_results.py --script legacy/plotting/regenerate_figures.py --figure ablation --results results/ablation/ablation/results.csv --out-dir results/ablation/figures
```

## 3. 准备本批训练专用攻击输入

```powershell
.venv/Scripts/python.exe prepare_attack_inputs.py --config configs/experiments/configs/beijing.json --releases configs/experiments/training_releases.json --out results/attack_inputs --out-config configs/experiments/attack_ready.json
```

## 4. 成员攻击

```powershell
.venv/Scripts/python.exe experiments/privacy_attack.py --config configs/experiments/attack_ready.json --batch attacks
```

## 5. 攻击作图

```powershell
.venv/Scripts/python.exe experiments/plot.py --config configs/experiments/attack_ready.json --experiment privacy_attack --batch attacks
```

## 6. 有序接口攻击

```powershell
.venv/Scripts/python.exe evaluation/run_bound_ordered_attack.py --config configs/experiments/attack_ready.json --out results/ordered_attack
```

## k 汇总

```powershell
.venv/Scripts/python.exe tools/collect_portable_sweeps.py --kind k --config configs/experiments/configs/beijing.json --plan configs/experiments/sweeps_plan.json --out results/summaries/k
```

## budget 汇总

```powershell
.venv/Scripts/python.exe tools/collect_portable_sweeps.py --kind budget --config configs/experiments/configs/beijing.json --plan configs/experiments/sweeps_plan.json --out results/summaries/budget
```

## endpoint_diagnostic 汇总

```powershell
.venv/Scripts/python.exe tools/collect_portable_sweeps.py --kind endpoint_diagnostic --config configs/experiments/configs/beijing.json --plan configs/experiments/sweeps_plan.json --out results/summaries/endpoint_diagnostic
```

## 预算作图

```powershell
.venv/Scripts/python.exe supplement/budget/render.py --source results/summaries/budget/summary.json --out results/figures/budget
```
