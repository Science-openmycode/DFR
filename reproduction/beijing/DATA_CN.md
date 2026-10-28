# 北京数据下载与预处理

[English](DATA.md) · [实验说明](../../README_CN.md)

以下命令在 `reproduction/beijing` 目录执行。原始数据、预处理数据、合成数据是三种不同对象：原始数据从 Microsoft 下载；预处理程序生成道路研究语料；各算法随后生成合成数据。真实数据及其时间戳不是 DP 发布物，不上传到合成数据目录。

## 1. 获取仓库与运行环境

先执行 `git clone https://github.com/Science-openmycode/DFR.git`，再在仓库根目录执行 `git lfs install` 和 `git lfs pull`，取得合成数据和公共资源。

进入 `reproduction/beijing`，按 README 第一节安装 Python 3.13.9 与锁定依赖。以下 `python` 表示已激活的该环境。

## 2. 下载 GeoLife 原始轨迹

来源：[Microsoft 官方下载页](https://www.microsoft.com/en-us/download/details.aspx?id=52367)。下载文件名为 **Geolife Trajectories 1.3.zip**，网页 Version 字段是 **1.2.2**，两者不要混淆。使用时保留压缩包内说明并遵守数据使用条件、引用原作者；本仓库不替数据提供方授权。

```powershell
python preprocess/fetch_geolife.py --archive data/downloads/geolife_1.3.zip --extract-to data/geolife
```

程序使用Microsoft下载地址；`--archive` 是保存位置，也可放入用户自行下载的压缩包；`--extract-to` 必须是新目录。用户不需要填写历史文件哈希。程序检查ZIP是否损坏及越界路径；可选的 `--expected-sha256` 仅供用户自己要求核验下载版本时使用，不是复现必需步骤。

预期得到 `data/geolife/Geolife Trajectories 1.3/Data/<用户>/Trajectory/*.plt`，原始 PLT 共 18,670 个文件（含空/不满足后续筛选的文件）；不要把原始文件数当北京有效轨迹数。官方概述的轨迹数与实际文件数属于不同统计口径。

## 3. 原始坐标与时间戳预处理

首先复用原有 GeoLife 解析程序，不改筛选算法：按路径排序，每个文件跳过六行头，保留北京范围内的点，至少两个点才保留轨迹，再用指定种子排列。

```powershell
python legacy/commands/prepare_geolife_beijing.py --source-dir "data/geolife/Geolife Trajectories 1.3/Data" --out data/raw/real_full_frozen.pkl --seed 20260713 --train-fraction 0.8 --bbox 39.75 40.15 116.10 116.65
python preprocess/recover_raw_metadata.py --source-dir "data/geolife/Geolife Trajectories 1.3/Data" --coordinates data/raw/real_full_frozen.pkl --out data/raw/metadata
```

第一条对本文使用的原始数据生成17,123条坐标轨迹；换输入后数量以实际产物为准。`--bbox` 顺序为纬度下界、纬度上界、经度下界、经度上界；`--seed` 固定排列；`--train-fraction` 是坐标批次划分比例。默认不要求用户的数据与作者历史文件逐字节一致。

第二条复用历史时间戳绑定逻辑，仅将硬编码路径改成参数。`--coordinates` 是第一条输出；`--out` 必须不存在。逐点精确比对后输出 `timestamps_day_serial.pkl.gz`、`original_observation_indices.pkl.gz`、`source_binding.csv`、`report.json`。时间戳来自 PLT 第五列（零基列号4），差值乘86400为秒。不完整绑定返回非零退出码。不要加载来源不可信的 pickle 文件。

MTNet还需要原始轨迹起止时间。它使用原实验按文件顺序和固定排列恢复身份的程序，不能仅用坐标查找源文件（不同轨迹可能有完全相同的坐标）：

```powershell
python preprocess/prepare_mtnet_time_binding.py --source-dir "data/geolife/Geolife Trajectories 1.3/Data" --reference data/raw/real_full_frozen.pkl --out data/raw/mtnet_time_binding.json
```

生成17123条起止时间及坐标摘要。此输出与前一条道路预处理用的逐点时间戳文件用途不同。

## 4. 获取对应的公共道路图

新版图已随仓库提供：[beijing_full_20261026.zip](../../public_assets/beijing_full_20261026.zip)，约31 MB。不是根目录旧 `public_assets/beijing_network`。公共 OSM 数据许可和来源见 [BEIJING_FULL_LICENSE.md](../../public_assets/BEIJING_FULL_LICENSE.md)。

```powershell
python preprocess/install_public_roads.py --out data/public
```

`--out` 必须是新目录；可用 `--archive` 指定同一压缩包的位置。程序校验固定哈希后解压，得到 `data/public/network/network.shp` 和同名配套文件，以及 `data/public/osm/osm_cache_beijing_drivable_full.pkl`。坐标系和道路编号沿用冻结图，不用新下载的当日 OSM 代替。

## 5. 道路预处理入口

本批次Windows匹配器位于 `resources/fmm` 和 `resources/stmatch`，包括对应FMMLIB.dll；不用根目录旧 `public_assets/matcher` 的匹配器替换它们。源项目为 [FMM/STMatch](https://github.com/cyang-kth/fmm)。先安装运行库（需要 conda）：

```powershell
conda create --prefix ./data/fmm-runtime --override-channels --channel conda-forge --repodata-fn repodata.json libgdal=2.4.4 boost-cpp=1.75.0 conda-launchers --yes
$env:PATH = "$PWD/data/fmm-runtime/Library/bin;$env:PATH"
$env:GDAL_DATA = "$PWD/data/fmm-runtime/Library/share/gdal"
$env:PROJ_LIB = "$PWD/data/fmm-runtime/Library/share/proj"
python prepare_roads.py --config configs/preprocess_beijing_8_16.json --out data/road_review --dry-run
python prepare_roads.py --config configs/preprocess_beijing_8_16.json --out data/road_review --review-only
```

`--config` 明确绑定坐标、时间戳、CSV、公共图、匹配程序与运行库；`--out` 为新目录；`--dry-run` 只显示参数，**不表示匹配成功**。配置固定全点、候选8→16、200m半径、50m GPS误差、8线程；不插入额外轨迹或读取其他批次的匹配结果。调整机器线程时只改配置中的 `threads`，不要修改匹配协议。

实际匹配输出分块证据、`reviewed_records.pkl.gz`、`selection.csv`、`selection_review.json` 和运行记录。筛选差异触发时退出2；用户阅读报告后自行决定是否接受道路子集。接受时不再需要填写哈希，执行：

```powershell
python prepare_roads.py --config configs/preprocess_beijing_8_16.json --out data/road_accepted --review-from data/road_review --accept-reviewed-subset yes
```

第二条只保存审核，不生成最终语料；第三条复用已保存记录，不加载或调用匹配器，只核验、投影和保存dataset。保留筛选报告，不把被剔除的轨迹隐瞒为全部保留。

时间参考：参数预览通常数秒，全量匹配按小时预留。历史4线程完成15,488/17,123条用时5.06小时，另一次8线程的515条困难轨迹重试用时1.98小时，两者不能相加当作本命令实测总时间。接受审核仅需读取、核验和投影，大语料按分钟至数十分钟预留（估计）。已有完整预处理语料可直接用于下文 `bind_dataset.py --dataset`，跳过匹配。仓库 `datasets/synthetic/` 与 `reference_results/` 可用于复算、作图，不能代替真实参考语料；目前没有提供预处理真实语料的下载包。旧版缺少复用证据的审核目录会明确报错，不会重新匹配。

历史新版冻结语料为15,730条道路轨迹，训练12,584、测试3,146；是否得到同一语料需核对实际匹配和筛选结果，不能强行截成该数。旧版17,123条不是新版道路语料。生成后可用 `bind_dataset.py --dataset ... --osm-cache ... --out ... --batch ...` 绑定新批次，再执行公共资源准备、TSTR划分与 README 后续命令；这些入口的完整参数见各自 `--help`。

## 6. 将新数据接入实验命令

以下假定上一节经人工审阅后生成的数据目录是 `data/road_accepted/dataset`。该目录不是dry-run产物。若实际目录不同，只修改下面 `--dataset`。新配置绑定新数据身份，不强行写成历史批次的ID。

MM2从作者固定版本下载，保留解压目录中的许可说明：

```powershell
python preprocess/fetch_mm2.py --archive data/downloads/mm2_1.2.1.zip --extract-to data/mm2_upstream --install-to resources/mm2/map_matching_2.exe
python bind_dataset.py --dataset data/road_accepted/dataset --osm-cache data/public/osm/osm_cache_beijing_drivable_full.pkl --runtime data/fmm-runtime/Library/bin --mm2 resources/mm2/map_matching_2.exe --mm2-network resources/mm2/network --out configs/local_new.json --batch local_new
python prepare_public_resources.py --config configs/local_new.json --frozen-support resources --out-config configs/local_public.json
python prepare_tstr_split.py --config configs/local_public.json --out data/local_split --out-config configs/local_split.json
python prepare_ubodt.py --config configs/local_split.json --out-dir data/local_ubodt --out-config configs/local_ready.json --delta-m 1500 --threads 4
python tools/write_batch_commands.py --config configs/local_ready.json --time-binding data/raw/mtnet_time_binding.json --raw-reference data/raw/real_full_frozen.pkl --out plans/local_new
```

- MM2为作者1.2.1版本，校验压缩包和程序；`--extract-to`必须是新目录。公共MM2网络随仓库LFS提供，绑定程序同时验证其与冻结道路图一致。
- `--batch`是新结果命名空间；所有输出配置必须不存在，避免覆盖旧实验。
- 已有预处理数据迁到另一机器后，可给 `bind_dataset.py` 增加 `--network data/public/network/network.shp`，只更新位置并核验原图字节，不改数据身份。后续公共资源、划分和攻击准备使用该配置路径。
- 公共缓存只包含道路图支持。`--frozen-support resources`逐项校验路网、OSM和缓存，不读取私有轨迹来构建查询支撑。
- TSTR步骤检查已有训练/测试划分，不重新随机划分。
- UBODT以原实验1500米生成，约6GB，须预留磁盘；`--threads`只控制并发。它不是合成数据。
- 最后一条**只生成命令文档和配置，不运行实验**。依次阅读 `plans/local_new/commands/` 中的统计M/R、DFR、原生基线、评分、TSTR和敏感性文档，复制其中完整命令运行。种子、预算和算法参数沿用原文，输入绑定和输出位置改为新批次。新结果写入 `results/local_new/`，不覆盖历史成绩。
- 该命令生成器不把旧结果重画称为新批次实验。隐私攻击需完成下面的独立输入绑定，不能使用不对应的旧真实集合。

### 6.1 新批次隐私攻击

先完成训练专用合成及来源登记。建立 `configs/local_attack_releases.json`，每个方法填写本批次的训练合成坐标文件和登记后的lineage，例如：

```json
{
  "MTR-DFR": {
    "coordinates": "results/local_new/实际训练发布目录/coordinates.pkl",
    "lineage": "results/local_new/实际训练发布目录/lineage.json"
  }
}
```

这里的路径需要替换为前述命令实际生成的位置；不得填写全集发布或旧批次。多个方法继续添加同结构条目。

```powershell
python prepare_attack_inputs.py --config configs/local_ready.json --releases configs/local_attack_releases.json --out data/local_attack --out-config configs/local_attack.json
python experiments/privacy_attack.py --config configs/local_attack.json --batch local_attack
python experiments/plot.py --config configs/local_attack.json --experiment privacy_attack --batch local_attack
```

第一条复用原攻击划分程序：种子20260715，训练集抽1000个成员，测试集抽1000个非成员，其余测试记录作为参考集；样本不足时按原程序缩小。三者索引互斥检查不变。第二条执行原攻击器并校验每个发布的训练来源；第三条只作图。输入、输出及索引都是内部研究材料，不是隐私合成发布的一部分。
