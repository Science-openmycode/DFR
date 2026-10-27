# MTR-DFR：按顺序复现实验

[English](README.md)

MTR-DFR 从差分隐私测量中生成道路级合成轨迹。仓库包含算法、基线实现、评估工具、已保存的合成数据和作图代码。下面依次完成安装、数据准备、合成、路由、评估和作图。

## 下载代码

先安装 [Git LFS](https://git-lfs.com/)，再在 PowerShell 中执行：

```powershell
git lfs install
git clone https://github.com/Science-openmycode/DFR.git
cd DFR
git lfs pull
cd reproduction/beijing
```

下文所有命令均在 `DFR/reproduction/beijing` 中运行，命令中的路径相对于该目录。

## 数据获取：先下载，再预处理

完整步骤在 [数据下载与预处理](reproduction/beijing/DATA_CN.md)：官方 GeoLife ZIP → 北京坐标轨迹 → 原始时间戳逐点绑定 → 冻结公共路网 → 全点道路预处理。提供真实下载地址、校验值、命令参数和每一步产物。

如果已经有授权的完整本地快照，也可以选择以下导入方式；它不是下载器：

```powershell
python import_external_assets.py --source "D:/authorized/beijing_delivery_20261018"
python import_external_assets.py --check-only
```

本目录包含算法代码、冻结道路数据、公共路网、统计与原生基线、评估代码、绘图函数和已经完成的实验结果。合成、路由、评估、作图分别执行。同一统计M输出可以选择五种R；MTR-DFR、DPMM、MTNet使用自身原生道路结果，不重新匹配。

## 1. 复制与安装

复制整个文件夹到另一台 **Windows x64** 机器。保留resources、legacy、vendor、reference_results、supplement、repairs、configs及代码说明；不用复制.venv、__pycache__、validation和之前的results。所有命令均在本文件夹运行，不需要原E盘工程、相邻目录、SSH或原服务器D盘路径。文件夹可以含中文和空格。

安装Python 3.13.9。Windows还需安装[微软Visual C++ x64运行库](https://aka.ms/vs/17/release/vc_redist.x64.exe)，按安装器提示完成；如系统要求管理员确认，由机器管理员操作。缺少它时，PyTorch可能报c10.dll初始化失败，安装Python依赖不能替代系统运行库。然后执行：

本教程的激活、GPU安装和GPU运行入口使用PowerShell脚本。若首次运行提示“此系统上禁止运行脚本”，先在执行机器查看`Get-ExecutionPolicy -List`。本机个人账户需要允许本地脚本时，由用户在PowerShell执行`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`并确认，再重新打开终端运行本教程；如果MachinePolicy或UserPolicy由组织配置，则由管理员处理。Python程序仍可用`.venv/Scripts/python.exe`直接运行。该设置不会由实验程序自动更改。

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-clean-windows-py313.txt
.venv/Scripts/python.exe -m pip install -r requirements-torch-cpu-py313.txt
.venv/Scripts/python.exe -m pip check
. .venv/Scripts/Activate.ps1
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
```

依赖版本由锁定文件指定。FMM/STMatch/MM2及公共资源位于resources；这些程序适用于Windows x64。只有MTNet训练需要NVIDIA GPU及兼容CUDA驱动；在运行MTNet前给本目录环境安装锁定GPU依赖：

```powershell
powershell -NoProfile -File deployment/SETUP_MTNET_GPU.ps1 -Root . -BasePython python
```

CPU版PyTorch用于PrivTrace官方程序的导入。MTNet的GPU安装会替换为锁定CUDA版本。安装、依赖检查与CUDA测试日志保存到setup_logs。安装需要访问软件源，实验计算不需要原服务器。

### 在运行实验的客户端完成安装检查

依赖安装在**实际运行代码的机器**：本机运行就在本机安装，远程运行就在远程机器安装。不要复制另一机器的`.venv`。按以下顺序准备：

1. 安装64位Python 3.13.9和上面的微软Visual C++ x64运行库。运行库安装器若提示重启，先重启；管理员确认由用户完成。
2. 执行上面的虚拟环境和两份Python依赖安装命令。
3. 执行以下检查，确认不只是安装清单无冲突，PyTorch还能够真正加载并计算：

```powershell
.venv/Scripts/python.exe -m pip check
.venv/Scripts/python.exe -c "import sys, torch; print(sys.executable); print('torch', torch.__version__); print('CPU_CHECK', (torch.ones(2)+1).tolist())"
```

4. FMM/STMatch按[DATA_CN.md](reproduction/beijing/DATA_CN.md)安装道路运行库，并在当前运行终端设置`GDAL_DATA`和`PROJ_LIB`；MM2使用该页的独立下载命令。
5. 只有需要MTNet训练时才运行上面的GPU安装脚本，然后执行：

```powershell
.venv/Scripts/python.exe -c "import torch; assert torch.cuda.is_available(), 'CUDA unavailable'; x=torch.ones(2, device='cuda'); print(torch.cuda.get_device_name(0)); print('GPU_CHECK', (x+1).cpu().tolist())"
```

预期显示显卡名称及`GPU_CHECK [2.0, 2.0]`。这仅确认GPU运行环境，不能代替MTNet训练和生成测试。

## 2. 从统计发布到道路轨迹

已有完整冻结快照时执行 [116条M/R与全集评分命令](reproduction/beijing/reproduction_checked_20261024/COMMANDS_CN.md)，每条列出参数、依赖和产物。从下载数据新建批次时，先完成 [DATA_CN.md 第6节](reproduction/beijing/DATA_CN.md)，再使用其生成的同名命令文档；不要把新数据接到旧批次ID下。

- SPRT、PrivTrace、DPTraj-PM、DPStd分别生成全集和训练专用M，共8份。
- 每份M选择Origin、Nearest、FMM、STMatch、MM2-MDP，共40份输出。R不读取真实数据。
- 随后的68条全集评分覆盖坐标统计、道路指标、物理轨迹结构与回顾性道路任务。

产物在results/reproduction_checked_20261024。已完成某个M时，可以复制其结果与manifest到另一机器，只继续未完成的R或评分。现有目录不覆盖，不必重跑已完成的M。

## 3. 原生道路方法

[DFR全集与训练生成](reproduction/beijing/REPRODUCE_DFR_LENGTH_20261024_CN.md) 使用冻结算法、length-aware分支和epsilon=1.4，随后接 [DFR三类评分](reproduction/beijing/REPRODUCE_NATIVE_SCORES_20261024_CN.md)。

[DPMM/MTNet生成](reproduction/beijing/REPRODUCE_NATIVE_BASELINES_20261024_CN.md) 分别列出全集/训练流程。DPMM使用加速实现；MTNet准备作者格式、训练并原生生成。各方法的隐私单位、delta分别保留，不因epsilon相同就宣称隐私保证等价。

## 4. 严格TSTR下游任务

新生成的统计方法按 [20个M×R训练专用评分命令](reproduction/beijing/REPRODUCE_TSTR_20261024_CN.md) 继续。道路编号仅转换为确定几何，再在合成训练集训练模型，在同一真实测试集评估。空槽位保留，不额外选路。

本目录同时包含完整23条件的实际训练发布及来源，包含DFR/DPMM/MTNet。按 [补充实验第1节](reproduction/beijing/SUPPLEMENT_COMMANDS_CN.md) 可重新评分这23份发布，也可跳过已完成评分，只重画保存结果。新结果写results，原成绩保留在reference_results。

要使用本次新生成的DFR/DPMM/MTNet，则继续 [原生生成到TSTR的逐条命令](reproduction/beijing/REPRODUCE_NATIVE_TSTR_CN.md)：执行记录、来源登记、确定几何转换、严格TSTR评分依次执行，不借用旧模型的lineage。

## 5. 隐私攻击与算法消融

[补充实验第2—3节](reproduction/beijing/SUPPLEMENT_COMMANDS_CN.md) 提供成员攻击、有序接口攻击和四组算法级消融。攻击输入在resources/attacks；不适用项保留NA。消融入口实际生成四组轨迹并评分，不是挑选旧表；随后独立作图命令读取生成的CSV。

## 6. 分辨率与隐私预算

- [K：六档×五种子，共30组](reproduction/beijing/supplement/sweeps/k_COMMANDS_CN.md)，K=24/48/96/192/384/768。
- [端点准确测量诊断，共3组](reproduction/beijing/supplement/sweeps/endpoint_diagnostic_COMMANDS_CN.md)，非私有诊断，单列。
- [预算：七档×五种子，共35组](reproduction/beijing/supplement/sweeps/budget_COMMANDS_CN.md)，epsilon=0.2/0.4/0.7/1/1.4/2/3。

每组依次执行生成、表示转换、道路评分、物理结构、坐标统计、道路任务六个独立命令，共408条。公共划分、原K核心及全部配置已在本目录，不需要旧服务器。随后按 [补充实验第4—5节](reproduction/beijing/SUPPLEMENT_COMMANDS_CN.md) 汇总新结果并绘制预算主图与76指标附录。已完成的K、预算结果在reference_results/k和reference_results/budget，复用时不重新生成。

## 7. M×R矩阵与图件

[补充实验第6节](reproduction/beijing/SUPPLEMENT_COMMANDS_CN.md) 使用完整保存矩阵、逐格原始评分JSON及原绘图函数，输出总矩阵、分组图、新旧对照图与cells.json。图件引用的数据和旧图也在本目录内。缺失/不适用与真实0分分开。

新批次应登记其真实结果，不能将reference_results的旧分数改名冒充新成绩。完整独立命令与预期文件集中在 [SUPPLEMENT_COMMANDS_CN.md](reproduction/beijing/SUPPLEMENT_COMMANDS_CN.md)。

[新批次矩阵命令](reproduction/beijing/REPRODUCE_NEW_MATRIX_CN.md) 从各新评分目录收集逐格来源，按原图型绘制并输出逐值变化；缺失保持缺失，多个批次的同一格冲突则报错。
