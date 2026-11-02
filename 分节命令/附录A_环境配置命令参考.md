# 附录A 环境配置命令参考

[完整运行指南](../README_CN.md#sec-A) · [上一节：10](第10节_小规模程序测试.md)

所有命令均在仓库的 `reproduction/beijing` 工作目录执行；文档位于仓库根目录，不要因为打开了分节文件就切换工作目录。北京默认，Porto只在第01节首次处理数据前选择一次配置。完整指南与分节版内容相同，选择一种阅读执行，不要两份都跑。

命令中的文件名和目录名沿用当前北京示例。`--config` 是配置，`--input` 是上游产物，`--out` 是新输出目录；自行改名时同步修改后续引用。每条命令成功并核对产物后再继续，已有成功产物按记录接续，不从头重复生成。

个别命令的 `--document` 指向仓库原命令文件，供执行来源登记使用；这些文件保留，无需跳过去阅读或再次执行。

环境已配置好时跳过本附录。以下为原有安装命令的集中参考，不是每次实验前都要重装。安装路径均以 `reproduction/beijing` 为例；不要在正在计算的环境中重装依赖。

## A.1 获取代码与大文件

```powershell
git lfs install
git clone https://github.com/Science-openmycode/DFR.git
cd DFR
git lfs pull
cd reproduction/beijing
```

最后一行进入后续所有命令的工作目录。

## A.2 创建环境、安装依赖并检查CPU

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-clean-windows-py313.txt
.venv/Scripts/python.exe -m pip install -r requirements-torch-cpu-py313.txt
.venv/Scripts/python.exe -m pip check
. .venv/Scripts/Activate.ps1
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
.venv/Scripts/python.exe -c "import sys, torch; print(sys.executable); print(torch.__version__); print('CPU_CHECK', (torch.ones(2)+1).tolist())"
```

前两份requirements分别锁定基础依赖与CPU版PyTorch。检查应输出 `CPU_CHECK [2.0, 2.0]`；确认sys.executable属于项目环境。PowerShell如禁止激活脚本，应按个人或组织策略配置执行权限，不绕过管理员限制。

## A.3 地图匹配运行库与当前终端变量

```powershell
conda create --prefix ./data/fmm-runtime --override-channels --channel conda-forge --repodata-fn repodata.json libgdal=2.4.4 boost-cpp=1.75.0 conda-launchers --yes
$env:PATH = "$PWD/data/fmm-runtime/Library/bin;$env:PATH"
$env:GDAL_DATA = "$PWD/data/fmm-runtime/Library/share/gdal"
$env:PROJ_LIB = "$PWD/data/fmm-runtime/Library/share/proj"
```

Conda负责安装所需的GDAL/Boost原生依赖。PATH让系统找到动态库，GDAL_DATA和PROJ_LIB指向其数据目录。安装只做一次；后三个变量在新终端需重新设置。另需自行安装Microsoft Visual C++ x64运行库。

## A.4 MTNet的GPU环境

```powershell
powershell -NoProfile -File deployment/SETUP_MTNET_GPU.ps1 -Root . -BasePython python
.venv/Scripts/python.exe -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0)); print((torch.ones(2, device='cuda')+1).cpu().tolist())"
```

`-Root .` 指当前实验工作目录；`-BasePython python` 用当前Python建立训练环境。第二条必须能实际在GPU上完成运算，不能只凭显卡存在判断。完成本清单后回到第01节1.2选择数据并开始处理。

---

[完整运行指南](../README_CN.md#sec-A) · [上一节：10](第10节_小规模程序测试.md)
