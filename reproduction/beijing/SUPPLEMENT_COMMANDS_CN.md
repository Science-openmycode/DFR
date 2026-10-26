# 补充实验：所有命令在本文件夹执行

先按README建立环境。本页不需要原E盘工程、旧服务器D盘目录或SSH。提供的reference_results是原实验保存结果；重跑时写入results，二者分开。相同冻结输入可直接复用已完成生成，按下面的独立评价/绘图命令继续。

## 1. 23条件严格TSTR

输入为目录内保存的23份训练专用发布及其实际生成来源，12,584训练、3,146测试。不会读取全集合成来替代训练专用发布。

```powershell
.venv/Scripts/python.exe experiments/tstr.py --config configs/portable_supplement.json --batch portable_tstr
```

生成 results/portable_tstr/tstr_audit_v2/results.csv、manifest.json 和 logs/tstr。随后对刚运行结果作图：

```powershell
.venv/Scripts/python.exe experiments/plot.py --config configs/portable_supplement.json --experiment tstr --batch portable_tstr
```

生成 results/portable_tstr/figures/tstr/06_strict_tstr.png、PDF。若只重画原先已经评分的结果，不执行前面评分：

```powershell
.venv/Scripts/python.exe tools/plot_executed_results.py --script legacy/plotting/regenerate_figures.py --figure tstr --results reference_results/tstr_audit_v2/results.csv --out-dir results/reference_figures/tstr
```

## 2. 成员攻击和有序接口攻击

成员/非成员/参考集和发布来源均在本目录resources/attacks及reference_results中；经验攻击不替代形式隐私证明。不适用结果为NA。

```powershell
.venv/Scripts/python.exe experiments/privacy_attack.py --config configs/portable_supplement.json --batch portable_attack
```

生成 results/portable_attack/privacy/results.csv、manifest.json，随后：

```powershell
.venv/Scripts/python.exe experiments/plot.py --config configs/portable_supplement.json --experiment privacy_attack --batch portable_attack
```

生成 results/portable_attack/figures/privacy/03_privacy_attacks.png、PDF。

```powershell
.venv/Scripts/python.exe evaluation/run_bound_ordered_attack.py --config configs/portable_supplement.json --out results/portable_ordered_attack
```

生成逐条件结果及总manifest；原攻击要求有序槽位对齐，不满足者保留NA，不丢弃槽位伪造可攻击性。

## 3. 算法级消融

固定epsilon=1.4、北京15730条、seed=42和length-aware分支，原四组算法消融实际生成并评价；不是从旧表里选择列。

```powershell
.venv/Scripts/python.exe run_dfr_ablation_frozen.py --config configs/portable_supplement.json --out results/portable_ablation/ablation
```

输出四组道路轨迹、results.csv、manifest.json。随后只读取该CSV作图：

```powershell
.venv/Scripts/python.exe tools/plot_executed_results.py --script legacy/plotting/regenerate_figures.py --figure ablation --results results/portable_ablation/ablation/results.csv --out-dir results/portable_ablation/figures
```

## 4. K分辨率

新数据或评分目录分开保存时，汇总命令可增加`--config <当前配置>`与`--plan <当前计划>`。计划每个cell的`directory`指向生成目录；可选`post_directory`指向表示转换和评分目录，`endpoint_partition`指向该组真正使用的公共划分。未指定时沿用本页标准布局。均值、五种子样本标准差和配对差的公式不变。源结果缺失时先完成对应计算，不填造结果。

执行 [30组逐条命令](supplement/sweeps/k_COMMANDS_CN.md)：K=24/48/96/192/384/768，每档5种子。公共层次JSON及原K实验核心已经放在目录内，不依赖原服务器。每组6步：生成、无选路的表示转换、道路评分、物理结构、坐标统计、道路任务。

```powershell
.venv/Scripts/python.exe tools/collect_portable_sweeps.py --kind k --out results/portable_sweeps/summary_k
```

生成summary.json、per_run.csv、manifest.json；五种子均值/样本标准差从新结果计算。另生成endpoint_diagnostics.json，使用原公式计算端点选中质量、噪声L1、两类fallback和六项指标相对K384的同种子配对差。这些私有诊断只用于研究，不是DP发布。原有已完成结果另存在reference_results/k。

端点准确测量诊断见 [3组独立命令](supplement/sweeps/endpoint_diagnostic_COMMANDS_CN.md)，它们不是DP发布，不与主实验混合。

```powershell
.venv/Scripts/python.exe tools/collect_portable_sweeps.py --kind endpoint_diagnostic --out results/portable_sweeps/summary_endpoint_diagnostic
```

## 5. 隐私预算

执行 [35组逐条命令](supplement/sweeps/budget_COMMANDS_CN.md)：epsilon=0.2/0.4/0.7/1/1.4/2/3，每档5种子。35次研究性发布不宣称合计仍只有单次预算。

```powershell
.venv/Scripts/python.exe tools/collect_portable_sweeps.py --kind budget --out results/portable_sweeps/summary_budget
```

生成summary.json和逐次CSV；随后使用原绘图函数绘制新汇总：

```powershell
.venv/Scripts/python.exe supplement/budget/render.py --source results/portable_sweeps/summary_budget/summary.json --out results/portable_sweeps/figures_budget
```

生成budget_main.png/PDF/SVG、全部76指标附录PDF/PNG及对照图。若仅重画已有完成结果：

```powershell
.venv/Scripts/python.exe supplement/budget/render.py --source reference_results/budget/summary.json --out results/reference_figures/budget
```

## 6. M×R总矩阵

此命令使用完整保存矩阵及其逐格原始评分JSON，检查每个来源，使用原绘图函数；不重新测量、不把不同方法的结果替换填入空格。

```powershell
.venv/Scripts/python.exe plotting/render_verified_matrix.py --sources reference_results/matrix --previous reference_results/matrix_previous --spec reference_results/matrix/spec.json --out results/reference_figures/matrix
```

生成current_full.png/PDF、逐组图、逐组新旧对照图及cells.json。reference_results/matrix_inputs包含矩阵各格真正使用的原结果文件。更换新批次时应重新登记该批次的结果来源，不能改旧成绩冒充新批次。
