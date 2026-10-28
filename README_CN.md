# MTR-DFR：按顺序复现实验

[English](README.md)

MTR-DFR 从差分隐私测量中生成道路级合成轨迹。按下面的顺序准备北京数据、生成合成数据、运行评估并作图。合成、路由、评估和作图分别执行。

## 1. 下载代码

先安装 [Git LFS](https://git-lfs.com/)，再在 PowerShell 执行。最后一行进入实验工作目录；后续所有命令都在该目录执行。


```powershell
git lfs install
git clone https://github.com/Science-openmycode/DFR.git
cd DFR
git lfs pull
cd reproduction/beijing
```

## 2. 安装 Python 环境

使用 Windows x64、Python 3.13.9。安装[微软 Visual C++ x64 运行库](https://aka.ms/vs/17/release/vc_redist.x64.exe)，按安装器要求重启。下列命令创建独立环境、安装锁定依赖并设置 UTF-8。


```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-clean-windows-py313.txt
.venv/Scripts/python.exe -m pip install -r requirements-torch-cpu-py313.txt
.venv/Scripts/python.exe -m pip check
. .venv/Scripts/Activate.ps1
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
```

## 3. 检查计算环境

最后应输出 `CPU_CHECK [2.0, 2.0]`。PrivTrace 导入时需要 PyTorch，不能省略 CPU 依赖安装。若 PowerShell 阻止本地脚本，先查看 `Get-ExecutionPolicy -List`；个人账户可自行设置 `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`，组织策略由管理员处理。


```powershell
.venv/Scripts/python.exe -c "import sys, torch; print(sys.executable); print(torch.__version__); print('CPU_CHECK', (torch.ones(2)+1).tolist())"
```

## 4. 下载 GeoLife 原始数据

来源是 [Microsoft GeoLife](https://www.microsoft.com/en-us/download/details.aspx?id=52367)。`--archive` 指定 ZIP 保存位置，`--extract-to` 指定新解压目录。输出 `data/geolife/Geolife Trajectories 1.3/Data/<user>/Trajectory/*.plt`。遵守数据提供方的使用和引用条款。


```powershell
python preprocess/fetch_geolife.py --archive data/downloads/geolife_1.3.zip --extract-to data/geolife
```

## 5. 解析坐标和时间戳

按北京范围筛选坐标，再恢复逐点时间戳和 MTNet 起止时间。`--bbox` 顺序是纬度下界、纬度上界、经度下界、经度上界。该 GeoLife 输入得到 17,123 条坐标轨迹；道路预处理会形成单独语料。


```powershell
python legacy/commands/prepare_geolife_beijing.py --source-dir "data/geolife/Geolife Trajectories 1.3/Data" --out data/raw/real_full_frozen.pkl --seed 20260713 --train-fraction 0.8 --bbox 39.75 40.15 116.10 116.65
python preprocess/recover_raw_metadata.py --source-dir "data/geolife/Geolife Trajectories 1.3/Data" --coordinates data/raw/real_full_frozen.pkl --out data/raw/metadata
python preprocess/prepare_mtnet_time_binding.py --source-dir "data/geolife/Geolife Trajectories 1.3/Data" --reference data/raw/real_full_frozen.pkl --out data/raw/mtnet_time_binding.json
```

## 6. 准备公共道路图和匹配运行库

公共图通过 Git LFS 随仓库提供，许可见 `public_assets/BEIJING_FULL_LICENSE.md`。先安装 Conda，再执行下列命令。得到 `data/public/network/network.shp`、OSM 缓存和 FMM/STMatch 运行库。环境变量只设置在当前终端。


```powershell
python preprocess/install_public_roads.py --out data/public
conda create --prefix ./data/fmm-runtime --override-channels --channel conda-forge --repodata-fn repodata.json libgdal=2.4.4 boost-cpp=1.75.0 conda-launchers --yes
$env:PATH = "$PWD/data/fmm-runtime/Library/bin;$env:PATH"
$env:GDAL_DATA = "$PWD/data/fmm-runtime/Library/share/gdal"
$env:PROJ_LIB = "$PWD/data/fmm-runtime/Library/share/proj"
```

## 7. 准备道路轨迹数据

先查看输入路径和参数，这一步通常只需几秒：

```powershell
python prepare_roads.py --config configs/preprocess_beijing_8_16.json --out data/road_review --dry-run
```

然后开始道路匹配。程序使用全部 GPS 点，先尝试 8 个候选道路，再对未成功的轨迹尝试 16 个候选道路；搜索半径为 200 米，GPS 误差参数为 50 米，使用 8 个线程。匹配记录和筛选报告保存在 `data/road_review`。全量数据需要预留数小时。

```powershell
python prepare_roads.py --config configs/preprocess_beijing_8_16.json --out data/road_review --review-only
```

打开 `data/road_review/selection_review.json`，查看哪些轨迹保留了、哪些被排除了。确认后运行下面的命令，直接用刚才保存的匹配结果生成道路数据集，无需重新匹配。若第二步返回退出码 2，读完筛选报告后也可用这条命令继续。

```powershell
python prepare_roads.py --config configs/preprocess_beijing_8_16.json --out data/road_accepted --review-from data/road_review --accept-reviewed-subset yes
```

完成后，数据保存在 `data/road_accepted/dataset`，其中包括道路轨迹、对应坐标，以及划分好的训练集和测试集。这一步预计需要几分钟到几十分钟。每次运行请给 `--out` 指定一个新目录。

已有本版本保存的 `road_review` 目录，可以从第三条命令继续。已有完整的 `dataset` 文件夹，就直接进入下一节，并使用生成这份数据时的公共路网。

如果只想重新评分或画图，可以用仓库里已经生成的合成数据 `datasets/synthetic/` 和实验结果 `reference_results/`。

## 8. 绑定新批次并生成逐条实验命令

下载 MM2，绑定输入与公共资源，检查固定划分，构建 UBODT，最后生成新批次命令。UBODT 约需6GB磁盘。`--batch` 控制结果命名；`--threads` 控制并发。各输出目录和配置使用新位置。最后一条只写出命令文档，不执行实验。


```powershell
python preprocess/fetch_mm2.py --archive data/downloads/mm2_1.2.1.zip --extract-to data/mm2_upstream --install-to resources/mm2/map_matching_2.exe
python bind_dataset.py --dataset data/road_accepted/dataset --osm-cache data/public/osm/osm_cache_beijing_drivable_full.pkl --runtime data/fmm-runtime/Library/bin --mm2 resources/mm2/map_matching_2.exe --mm2-network resources/mm2/network --out configs/local_new.json --batch local_new
python prepare_public_resources.py --config configs/local_new.json --frozen-support resources --out-config configs/local_public.json
python prepare_tstr_split.py --config configs/local_public.json --out data/local_split --out-config configs/local_split.json
python prepare_ubodt.py --config configs/local_split.json --out-dir data/local_ubodt --out-config configs/local_ready.json --delta-m 1500 --threads 4
python tools/write_batch_commands.py --config configs/local_ready.json --time-binding data/raw/mtnet_time_binding.json --raw-reference data/raw/real_full_frozen.pkl --out plans/local_new
```

## 9. 按生成文档运行统计 M 和 R

打开 `plans/local_new/commands/reproduction_checked_20261024/COMMANDS_CN.md`，从上到下复制执行每条命令。四种 M 各生成全集和训练专用输出，共8份；每份选择 Origin、Nearest、FMM、STMatch、MM2-MDP，共40份路由结果，然后运行文档中的全集评分。M 写出 `measurement.pkl`，R 写出坐标或 `synthetic_routes.pkl.gz`。核心 R 只使用 M 输出与公共道路资源；冻结批次入口还检查数据目录和划分信息。

## 10. 运行 DFR、DPMM 和 MTNet

先执行 `plans/local_new/commands/REPRODUCE_DFR_LENGTH_20261024_CN.md`，再执行 `REPRODUCE_NATIVE_BASELINES_20261024_CN.md`。DFR 使用 `--length-aware`，总预算 ε=1.4。DPMM先完成当前输入的60条等价验证；训练生成前后按文档记录退出码。MTNet需要NVIDIA GPU；训练前执行下列安装和运算检查，随后继续文档的准备、导出、30轮训练及原生生成。各方法保留其隐私单位和δ。


```powershell
powershell -NoProfile -File deployment/SETUP_MTNET_GPU.ps1 -Root . -BasePython python
.venv/Scripts/python.exe -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0)); print((torch.ones(2, device='cuda')+1).cpu().tolist())"
```

## 11. 运行全集效用评估

执行 `plans/local_new/commands/REPRODUCE_NATIVE_SCORES_20261024_CN.md`。DFR和MTNet分别计算道路、坐标统计、物理结构与回顾性道路任务。DPMM当前导出坐标数组，先保留所有输出槽位，再计算坐标统计；没有原生道路ID的项目保留缺失，不额外匹配。每个评分程序只读取已生成数据。

## 12. 运行严格 TSTR

依次执行 `plans/local_new/commands/REPRODUCE_TSTR_20261024_CN.md` 和 `REPRODUCE_NATIVE_TSTR_CN.md`。合成器只读取真实训练集，下游模型在合成训练集上训练，在同一真实测试集评估。原生方法先登记来源，再做确定几何转换。输出每个条件的 `results.csv` 和 `manifest.json`；真实训练数据训练出的模型作为共同参考。

## 13. 运行消融和隐私攻击

执行新生成的 `plans/local_new/commands/SUPPLEMENT_COMMANDS.md` 前六节：四组算法级消融生成与评估、消融作图、23条件训练发布的攻击输入准备、成员攻击、攻击作图和有序接口攻击。`training_releases.json` 指向本批次真实产物。攻击不适用项保留NA；经验攻击与数学隐私证明分别解释。

## 14. 运行分辨率和隐私预算实验

按顺序执行 `plans/local_new/commands/supplement/sweeps/` 内的 `k_COMMANDS_CN.md`、`budget_COMMANDS_CN.md`、`endpoint_diagnostic_COMMANDS_CN.md`。K=24/48/96/192/384/768，每档5种子；ε=0.2/0.4/0.7/1/1.4/2/3，每档5种子；准确端点诊断3组，单列为非私有诊断。每组按生成、表示转换、道路评分、物理结构、坐标统计、道路任务六步执行。

## 15. 汇总敏感性结果并作图

继续执行 `plans/local_new/commands/SUPPLEMENT_COMMANDS.md` 中的三类汇总与预算作图命令。这些命令显式读取当前配置和 `sweeps_plan.json`，输出本批次summary、逐次CSV、预算主图与76指标附录。多种子结果属于研究比较，隐私预算按实际发布次数组合。

## 16. 收集矩阵并生成图件

最后执行 `plans/local_new/commands/REPRODUCE_NEW_MATRIX_CN.md`，从新评分目录收集来源并作图。当前冻结规格是27行×45列；统计方法分别显示M×R，DFR、DPMM、MTNet各一行。每格保留评分来源，0、NA和缺失分别显示。结果写入新批次目录；保存结果位于 `reference_results/`。

## 17. 小规模程序测试

安装运行库后，可用人工夹具检查程序接口。`SMALL_CLI_CN.md` 提供逐条小规模生成和路由命令；下列命令运行回归测试。小规模测试与数据集级实验结果分开保存。


```powershell
$env:DFR_TEST_RUNTIME = "$PWD/data/fmm-runtime/Library/bin"
python -m pytest tests -q
```
