# 北京 MTR-DFR 完整实验目录

先检查安装和小规模生成可按 [小规模命令行检查](SMALL_CLI_CN.md) 逐条执行；它不运行全量论文实验，也不以help输出代替生成成功。

## 数据获取：先下载，再预处理

完整步骤在 [数据下载与预处理](DATA_CN.md)：官方 GeoLife ZIP → 北京坐标轨迹 → 原始时间戳逐点绑定 → 冻结公共路网 → 全点道路预处理。提供真实下载地址、校验值、命令参数和每一步产物。

公共路网压缩包现已随仓库提供；原始轨迹从Microsoft获取，不再要求读者先找到作者E盘目录。旧坐标批次为17,123条，新版道路批次历史结果为15,730条，不能混用。仓库为私密，协作者需要GitHub访问权限。

如果已经有授权的完整本地快照，也可以选择以下导入方式；它不是下载器：

```powershell
python import_external_assets.py --source "D:/authorized/beijing_delivery_20261018"
python import_external_assets.py --check-only
```

导入器检查external_assets.json中的各文件。完整9.42GB历史快照尚未全部在线分发；下文对冻结数据/结果的描述在相应资源已导入或重新生成后成立。仅完成原始数据下载不代表全部模型、匹配运行库和实验结果已获得。

本目录包含算法代码、冻结道路数据、公共路网、统计与原生基线、评估代码、绘图函数和已经完成的实验结果。合成、路由、评估、作图分别执行。同一统计M输出可以选择五种R；MTR-DFR、DPMM、MTNet使用自身原生道路结果，不重新匹配。

迁移验证范围见 [迁移报告](PORTABILITY_REPORT_CN.md)，本轮三处新批次接续的实现和测试见 [接续报告](CONNECTION_REPORT_CN.md)。保存结果复评与从零重新完成正式实验不同，接口验证不冒充长实验重跑。

## 1. 复制与安装

复制整个文件夹到另一台 **Windows x64** 机器。保留resources、legacy、vendor、reference_results、supplement、repairs、configs及代码说明；不用复制.venv、__pycache__、validation和之前的results。所有命令均在本文件夹运行，不需要原E盘工程、相邻目录、SSH或原服务器D盘路径。文件夹可以含中文和空格。

本交付绑定北京预处理后的15,730条道路轨迹，严格TSTR使用12,584条训练、3,146条测试。目录内含私有研究数据和来源记录，供授权研究，不自动公开上传。北京配置不能直接代表其它城市。

安装Python 3.13.9，然后执行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-clean-windows-py313.txt
.venv/Scripts/python.exe -m pip check
. .venv/Scripts/Activate.ps1
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
```

依赖版本由锁定文件指定。FMM/STMatch/MM2及公共资源位于resources；提供的是Windows程序，不冒称Linux原生程序。只有MTNet训练需要NVIDIA GPU及兼容CUDA驱动；在运行MTNet前给本目录环境安装锁定GPU依赖：

```powershell
powershell -NoProfile -File deployment/SETUP_MTNET_GPU.ps1 -Root . -BasePython python
```

安装、依赖检查与CUDA测试日志保存到setup_logs。安装需要访问软件源，实验计算不需要原服务器。

## 2. 从统计发布到道路轨迹

已有完整冻结快照时执行 [116条M/R与全集评分命令](reproduction_checked_20261024/COMMANDS_CN.md)，每条列出参数、依赖和产物。从下载数据新建批次时，先完成 [DATA_CN.md 第6节](DATA_CN.md)，再使用其生成的同名命令文档；不要把新数据接到旧批次ID下。

- SPRT、PrivTrace、DPTraj-PM、DPStd分别生成全集和训练专用M，共8份。
- 每份M选择Origin、Nearest、FMM、STMatch、MM2-MDP，共40份输出。R不读取真实数据。
- 随后的68条全集评分覆盖坐标统计、道路指标、物理轨迹结构与回顾性道路任务。

产物在results/reproduction_checked_20261024。已完成某个M时，可以复制其结果与manifest到另一机器，只继续未完成的R或评分。现有目录不覆盖，不必重跑已完成的M。

## 3. 原生道路方法

[DFR全集与训练生成](REPRODUCE_DFR_LENGTH_20261024_CN.md) 使用冻结算法、length-aware分支和epsilon=1.4，随后接 [DFR三类评分](REPRODUCE_NATIVE_SCORES_20261024_CN.md)。

[DPMM/MTNet生成](REPRODUCE_NATIVE_BASELINES_20261024_CN.md) 分别列出全集/训练流程。DPMM使用已验证的加速实现；MTNet准备作者格式、训练并原生生成。各方法的隐私单位、delta分别保留，不因epsilon相同就宣称隐私保证等价。

## 4. 严格TSTR下游任务

新生成的统计方法按 [20个M×R训练专用评分命令](REPRODUCE_TSTR_20261024_CN.md) 继续。道路编号仅转换为确定几何，再在合成训练集训练模型，在同一真实测试集评估。空槽位保留，不额外选路。

本目录同时包含完整23条件的实际训练发布及来源，包含DFR/DPMM/MTNet。按 [补充实验第1节](SUPPLEMENT_COMMANDS_CN.md) 可重新评分这23份发布，也可跳过已完成评分，只重画保存结果。新结果写results，原成绩保留在reference_results。

要使用本次新生成的DFR/DPMM/MTNet，则继续 [原生生成到TSTR的逐条命令](REPRODUCE_NATIVE_TSTR_CN.md)：执行记录、来源登记、确定几何转换、严格TSTR评分依次执行，不借用旧模型的lineage。

## 5. 隐私攻击与算法消融

[补充实验第2—3节](SUPPLEMENT_COMMANDS_CN.md) 提供成员攻击、有序接口攻击和四组算法级消融。攻击输入在resources/attacks；不适用项保留NA。消融入口实际生成四组轨迹并评分，不是挑选旧表；随后独立作图命令读取生成的CSV。

## 6. 分辨率与隐私预算

- [K：六档×五种子，共30组](supplement/sweeps/k_COMMANDS_CN.md)，K=24/48/96/192/384/768。
- [端点准确测量诊断，共3组](supplement/sweeps/endpoint_diagnostic_COMMANDS_CN.md)，非私有诊断，单列。
- [预算：七档×五种子，共35组](supplement/sweeps/budget_COMMANDS_CN.md)，epsilon=0.2/0.4/0.7/1/1.4/2/3。

每组依次执行生成、表示转换、道路评分、物理结构、坐标统计、道路任务六个独立命令，共408条。公共划分、原K核心及全部配置已在本目录，不需要旧服务器。随后按 [补充实验第4—5节](SUPPLEMENT_COMMANDS_CN.md) 汇总新结果并绘制预算主图与76指标附录。已完成的K、预算结果在reference_results/k和reference_results/budget，复用时不重新生成。

## 7. M×R矩阵与图件

[补充实验第6节](SUPPLEMENT_COMMANDS_CN.md) 使用完整保存矩阵、逐格原始评分JSON及原绘图函数，输出总矩阵、分组图、新旧对照图与cells.json。图件引用的数据和旧图也在本目录内。缺失/不适用与真实0分分开。

新批次应登记其真实结果，不能将reference_results的旧分数改名冒充新成绩。完整独立命令与预期文件集中在 [SUPPLEMENT_COMMANDS_CN.md](SUPPLEMENT_COMMANDS_CN.md)。

[新批次矩阵命令](REPRODUCE_NEW_MATRIX_CN.md) 从各新评分目录收集逐格来源，按原图型绘制并输出逐值变化；缺失保持缺失，多个批次的同一格冲突则报错。

## 8. 迁移检查与记录

[迁移报告](PORTABILITY_REPORT_CN.md) 记录实际搬迁检查、原工程读取隔离、失败与修复。已验证且未受迁移影响的正式实验没有重跑，参数入口检查不计作正式实验。

旧说明保存为README_BEFORE_PORTABILITY_20261024.md、README_HISTORY_20261024.md，只是历史记录，不是当前教程。本README与补充命令使用文件夹内路径。
