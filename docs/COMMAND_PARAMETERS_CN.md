# MTR-DFR 命令行参数与跨任务迁移

## 1. 路径和独立运行规则

- `commands/reproduce.py` 以自身位置寻找代码和资产，不依赖启动时的当前目录。从任意目录调用时，可把脚本写成绝对路径。
- 传给子命令的绝对路径保持不变；相对路径统一相对于本复现文件夹根目录，而不是调用者的当前目录。
- 所有真实数据只作为显式参数输入。代码不会从仓库外的固定盘符读取数据。
- 迁移到新城市时，必须成组替换真实轨迹、`bbox`、OSM/道路网络、匹配路线和 edge cache；这些文件必须共享同一坐标系和道路 ID 空间。
- `--` 用于分隔总入口参数和被调用实验程序的参数。参数值含空格时必须加引号。

## 2. MTR-DFR 生成参数

建立北京道路参考前，按 README 的命令用 conda-forge 创建 `libgdal=2.4.4`、`boost-cpp=1.75.0` 运行时，将 `Library/bin` 中的两个匹配器 DLL 复制到 conda 前缀根目录，并设置 PATH、GDAL_DATA 和 PROJ_LIB。`verify-matcher -- --runtime-dir DIR` 会实际启动包内 FMM 与 STMatch。随后运行 `prepare-road-reference`；其 `--real` 是真实坐标轨迹，`--network` 是同城公共有向道路图，`--stmatch-bin` 是匹配器可执行文件，`--runtime-dir` 是上述 conda 前缀。`--max-points`、`--radius-m`、`--gps-error-m`、`--candidates` 固定匹配模型；`--batch-size` 和 `--omp-threads-per-worker` 控制批量与 CPU 并行；`--out-dir` 写出 `matched_paths/Real.pkl.gz`。北京全量参考已按 `20000/8` 的批量/线程设置验证。

| 参数 | 示例值 | 含义与迁移规则 |
|---|---:|---|
| `--real-matched` | `C:\data\Real.pkl.gz` | 私有的有向道路 ID 轨迹；迁移任务时须用新城市同一公共图完成匹配。 |
| `--edge-cache` | `public_assets/...pkl.gz` | 公共边、区域和路线族缓存；必须与 `--real-matched` 和 `--network` 使用同一边 ID 空间。 |
| `--network` | `network.shp` | 公共道路矢量文件，用于边几何和坐标恢复。 |
| `--seed` | `20260719` | 一次可复现实验的 DP 噪声与生成种子；与 `--formal/--check-only` 三选一。 |
| `--formal` | 开关 | 运行实现定义的正式模式；不与 `--seed` 同时使用。 |
| `--check-only` | 开关 | 只验证依赖和显式路径，不读取私有轨迹。 |
| `--length-aware` | 开关 | 启用长度感知的公共后处理；比较时必须在所有对应实验中保持一致。 |
| `--public-slot-count` | `17123` | 预先声明的固定道路轨迹输出数；迁移任务时显式设置，不从私有输入条数推断。 |
| `--out-dir` | `C:\runs\mtr_dfr` | 独立输出目录；相对路径按复现文件夹根目录解释。 |

道路路线转坐标使用 `routes-to-coordinates`：`--routes` 是道路 ID 路线，`--network` 是道路矢量文件，DFR 路线还须用 `--edge-cache` 指向生成该路线的同一公共端点缓存，以便把规范边端点映射回 shapefile 几何；`--out` 是坐标轨迹输出。程序拒绝无法在公共图上实现的路线，并为坐标文件生成同名 `.manifest.json`，记录路线、地图、边缓存及输出哈希。严格划分道路路线使用 `subset-routes`：`--matched-full` 是全量匹配路线，`--split-manifest` 是轨迹划分索引，`--out` 是 train-only 路线。

## 3. Baseline 生成参数

| 参数 | 示例值 | 含义与迁移规则 |
|---|---:|---|
| `--method` | `sprt-native` | 算法入口。正文四种原生方法为 `sprt-native`、`privtrace-native`、`dptrajpm-native`、`dpstd-native`。 |
| `--data` | `C:\data\real.pkl` | 输入真实坐标轨迹；严格 TSTR 必须换成 train-only 文件。 |
| `--epsilon` | SPRT/DPTraj-PM/DPStd 用 `1.4`；保留 PrivTrace 用 `1.0` | 该 baseline 的生成预算。本轮 PrivTrace 未更换预算，因此不能将这一混合批次称为等预算比较。 |
| `--seed` | `42` | 随机种子；多次重复实验逐次更换。 |
| `--bbox` | `39.75 40.15 116.10 116.65` | 公共城市范围，顺序为纬度最小、纬度最大、经度最小、经度最大；陌生数据集必填。 |
| `--osm-cache` | `generation/baselines/data/osm/osm_cache_beijing.pkl` | 与 bbox 一致的公共 OSM 缓存；陌生数据集必填。相对路径相对于本复现文件夹。 |
| `--public-slot-count` | `17123` | 在读取私有数据前预声明的合成条数；严格 TSTR 北京训练侧为 `13698`，陌生数据集必填。 |
| `--out-dir` | `C:\runs\baselines\sprt-native` | 独立输出目录。 |
| `--tag` | 可选 | 输出标识，不改变算法。 |
| `--format` | `pkl` | 输出为 `pkl`、`npz` 或 `both`。 |
| `--extra-arg` | 可重复 | 原样传给特定复现适配器的附加参数，格式由该适配器定义。 |

## 4. 数据划分与攻击参数

| 入口与参数 | 含义 |
|---|---|
| `prepare-geolife --source-dir` | 官方 GeoLife 1.3 解压后的 `Data` 目录；本命令不读取仓库外的研究缓存。 |
| `prepare-geolife --out` | 北京输入 `real_full_frozen.pkl` 的新路径；已有文件不会被覆盖。配合 `--check-only` 可省略。 |
| `prepare-geolife --seed/--train-fraction` | 冻结输入的顺序：默认种子 `20260713`，训练比例 `0.8`，训练部分接测试部分。 |
| `prepare-geolife --bbox/--limit` | 四个边界值 `lat_min lat_max lon_min lon_max`，默认北京范围；`--limit` 只用于小规模检查。 |
| `prepare-geolife --expected-sha256/--check-only` | 前者在写入前核对预期哈希；后者只计算哈希、不保存轨迹。 |
| `prepare-split --data` | 待划分真实轨迹。 |
| `prepare-split --input-order` | 输入由 `prepare-geolife` 生成的论文冻结文件时，按原有“训练部分接测试部分”的顺序切分，避免二次随机打乱；任意未预分组数据省略此项。 |
| `prepare-split --train-fraction` | 训练比例，默认 `0.8`；其余记录形成互斥测试集。 |
| `prepare-split --seed` | 固定划分顺序的随机种子，默认 `20260713`。 |
| `prepare-split --out-dir` | 写出 `train.pkl`、`test.pkl`、`split_manifest.json` 的目录。 |
| `prepare-attack-split --split-dir` | 上一步的严格划分目录。 |
| `prepare-attack-split --attack-candidates` | 每组攻击候选数量，默认 `1000`。 |
| `prepare-attack-split --seed` | 攻击候选抽样种子，默认 `20260715`。 |
| `prepare-attack-split --out-dir` | member、nonmember、reference 文件输出目录。 |
| `run-privacy --method` | 单个无名称 `--release PATH` 的图表方法名；批量输入时用 `NAME=PATH`，无需该项。 |
| `run-privacy --members/--nonmembers/--reference` | 三个互斥攻击集合。 |
| `run-privacy --release` | 被攻击的合成发布；可重复传入 `NAME=PATH`，每个发布独立运行并汇总到 `results.csv`。 |
| `run-privacy --bbox` | 四项顺序为 `lat_min lat_max lon_min lon_max`。 |
| `run-privacy --seed` | 攻击模型随机种子，默认 `20260724`。 |
| `run-privacy --out-dir` | 新攻击结果目录。 |

## 5. 统一评估与实验参数

### FMM 路线重建

- `prepare_road_evaluation_network.py --dataset-config/--out-dir`：从配置中的公共 OSM 缓存生成 FMM 专用有向分段路网；输出目录必须是新目录。
- `--ubodt-format csv --ubodt-delta-m 1000 --ubodt-bin public_assets\matcher\ubodt_gen.exe`：生成 FMM 可读取的 CSV UBODT。路网与 UBODT 必须来自同一次构建。
- `explore_fmm_road_alignment.py --network/--ubodt/--fmm/--fmm-runtime-dir`：分别指定上述路网、配套 UBODT、FMM 可执行文件和运行库目录。
- `--routes-out-dir DIR`：把新匹配路线写到 `DIR\matched_paths\<方法>.pkl.gz`，供 M×R/TSTR 后续步骤直接读取；`--out-dir` 单独保存诊断结果。

| 入口与参数 | 含义与迁移规则 |
|---|---|
| `evaluate --real/--synthetic` | 真实参考与一份合成轨迹。两者必须为同一城市和坐标系。 |
| `evaluate --witness` | 可选道路 witness；只有发布 witness 的方法传入。 |
| `evaluate --road-routes/--edge-cache` | 可选有向道路路线与公共边缓存；用于由 `routes-to-coordinates` 派生坐标的发布，要求同名 derivation manifest 的哈希和槽位数一致。与 `--witness` 互斥。 |
| `evaluate --dataset-config` | 可选数据集配置键；注册数据集用它加载冻结公共设置。任意新数据集可省略并显式提供后述三项。 |
| `evaluate --bbox/--osm-cache/--public-slot-count` | 任意新数据集必须显式给出城市范围、公共道路缓存和预声明评估条数。 |
| `evaluate --task-mode` | 当前为 `retrospective`；严格泛化任务使用独立的 `run-tstr`。 |
| `evaluate --evaluation-seed` | 评估抽样随机种子，默认 `20260713`。 |
| `evaluate --cdtw-samples` | cDTW 真实样本数，默认 `400`。 |
| `evaluate --cdtw-candidates` | 每条轨迹比较的候选数，默认 `24`。 |
| `evaluate --cdtw-od-grid` | cDTW 的 OD 分层网格分辨率，默认 `12`。 |
| `evaluate --out-dir/--log-file` | 指标目录和可选日志文件。 |
| `run-profile --real` | 统一真实参考。 |
| `run-profile --synthetic` | `NAME=PATH`，每个方法重复一次。 |
| `run-profile --witness` | `NAME=PATH`，只为有 witness 的同名方法提供；坐标与 witness 必须位于同一发布目录且通过其 manifest 哈希核对。 |
| `run-profile --road-routes/--edge-cache` | `--road-routes NAME=PATH` 提供与坐标文件对应的有向道路路线，`--edge-cache` 指定同一道路图的公共边缓存；需要由 `routes-to-coordinates` 生成的同名 derivation manifest 绑定两者。 |
| `run-profile --dataset-config/--bbox/--osm-cache/--public-slot-count` | 注册数据集可用配置键；任意新数据集显式给出范围、同城道路缓存和评估条数。 |
| `run-profile --out-dir` | 逐方法 raw 指标与汇总 CSV 目录。 |
| `run-framework --real-routes` | 真实匹配道路路线参考。 |
| `run-framework --edge-cache` | 可选公共 edge cache；省略时使用包内北京资产。迁移城市必须显式提供。 |
| `run-framework --routed` | `NAME=ROUTE_PICKLE`，对每个已路由方法重复。 |
| `run-framework --out-dir` | 框架提升结果目录。 |
| `run-mr --real-routes` | 真实匹配道路路线。 |
| `run-mr --edge-cache` | 与所有路线对象共享边 ID 的公共缓存。 |
| `run-mr --network` | 公共有向道路网 shapefile，至少含 `id` 和 `length_m`；默认北京公开道路网。由边 ID 与公共缓存映射到边长，用于路线形态保留率。迁移城市时与 `--edge-cache` 一起替换。 |
| `run-mr --route` | `M::R=PATH`，显式加入一个测量—路由组合，可重复。 |
| `run-mr --route-dir` | 批量扫描 `<M>/<R>.pkl[.gz]` 的根目录；只有未给 `--route` 时才默认读取包内路线。显式 `--route` 不自动混入历史缓存。 |
| `run-mr --out-dir` | M×R 原始值和矩阵目录。 |

`run-mr` 的 `results.csv` 直接从输入路线重新计算道路有效率、OD24 需求覆盖率 `DemandFid`、BTF、RC/Edge/Turn/Family CPC、道路边和转向的召回率/精确率/F1/IoU、分支条件保真度 `BranchCPC`、主导出口准确率 `ExitAcc`，以及 OD 条件化区域前缀保真度 `ODPF96/ODPF384`。这些列使用同一组显式提供的路线对象，不从冻结表摘取。
`RC-CPC` 与 BTF 对同一条轨迹的路口选择赋单位总质量；长轨迹不会因路口较多而在条件分布比较中被额外加权。
`run-mr` 还从同一批路线与 `--network` 重算总长度、消环后骨干长度、闭合段长度、闭合段数量和重复道路边出现次数的真实/合成均值比。

`run-physical` 从显式路线对象计算完整公共 OD 分层的有序道路公里数、路口转向及消环骨干的恢复率与支持率。必填 `--real-routes`、`--synthetic-routes`、`--method`、`--out-dir`；`--edge-cache` 与 `--network` 指向同城公共图，默认北京资产；`--cap-per-stratum` 默认为每侧 20 条、至少为 2；`--sampling-label` 默认等于 `--method`，用于固定同一 OD 层内的定额样本。
| `run-ablation --data/--dataset-config/--bbox/--osm-cache` | DFR 消融的显式真实坐标数据和同城公共配置。 |
| `run-ablation --epsilon-total/--noise-seed/--decoder-seed/--request-seed/--public-slot-count` | DFR 各臂共用的隐私预算、随机种子和固定输出规模。 |
| `run-ablation --limit` | 仅用于小规模功能检查，且必须等于 `--public-slot-count`；正式实验不使用。 |
| `run-ablation --variants` | DFR 算法级消融臂，可选 `no-endpoint-measurement endpoint-measurement-only family-measured-unmatched-router full`。 |
| `run-ablation --reuse-generated` | 在同一 `--out-dir` 复用已生成的 DFR 算法臂，不重新合成；程序校验路线槽位数，记录各臂和真实参考的 SHA-256 后重算指标。 |
| `run-ablation --real-routes/--edge-cache/--network` | DFR 消融需要真实匹配路线、公共缓存和同一有向道路图。 |
| `run-ablation --seed/--length-aware/--public-slot-count` | DFR 各臂共用的噪声种子、长度组件开关和固定输出规模。 |
| `run-ablation --variants` | DFR 实际重新合成的算法臂，可选 `no-endpoint-measurement endpoint-measurement-only family-measured-unmatched-router full`。 |
| `run-ablation --out-dir` | 各臂新合成数据、逐臂指标、聚合 CSV 和 manifest 的目录。 |
| `run-tstr --train-real/--test-real` | 严格互斥的真实训练/测试轨迹；合成器只能读取 train。 |
| `run-tstr --synthetic` | 合成训练语料路径；每个方法重复一次。 |
| `run-tstr --names` | 与 `--synthetic` 完全同序、同数量的方法名。 |
| `run-tstr --osm-cache/--bbox` | 测试城市的公共道路缓存和范围。 |
| `run-tstr --seed` | 下游模型训练与抽样种子，默认 `20260713`。 |
| `run-tstr --out-dir` | 逐任务模型输出和 TSTR 汇总目录。 |
| `run-structure --dataset` | `NAME=PATH`，Real 与各合成语料各重复一次。 |
| `run-structure --out-dir` | 逐轨迹结构诊断和汇总目录。 |

## 6. 作图参数

| 参数 | 含义 |
|---|---|
| `plot --figure` | `evidence/framework/privacy/profile/mr/ablation/tstr/structure/all` 之一。 |
| `plot --data-root` | 本轮真实运行结果根目录；指定后若缺失对应结果会直接报错，不回退到冻结数值。 |

## 7. 最小跨城市替换清单

1. 用新城市真实轨迹替换 `--data`、`--real`、`--train-real`、`--test-real`。
2. 用新城市范围替换所有 `--bbox`，顺序固定为纬度最小、纬度最大、经度最小、经度最大。
3. 用新城市公共图替换 `--osm-cache` 或 `--network`，并重建同图的 `--edge-cache`。
4. 所有 `--real-routes`、`--real-matched` 和 `--routed/--route` 文件必须由同一图产生。
5. 预先声明 `--public-slot-count`，记录全部随机种子、隐私预算和输出目录。
6. 先运行 `--check-only`（DFR）或小规模 smoke test，再执行完整生成；随后依次运行评估、实验聚合与作图。
## 发布来源与矩阵输入检查

每个 `run-tstr` 名称必须唯一，与重复的 `--synthetic` 一一对应。`--road-synthetic` 可为道路任务提供完整边顶点坐标视图；若提供，次数须等于 `--synthetic`，且每对视图的路由前发布 SHA 相同。

`evaluation/combine_tstr_mr.py` 的 `--native/--fmm/--stmatch` 是三次任务评分生成的 results.csv；`--out-dir` 是六指标矩阵、七指标长表与输入绑定 manifest 的输出目录。相对路径以本独立目录为根。三个输入必须共享 train/test、bbox、seed、OSM 和 base_releases。生成器的训练数据谱系是另一个检查项，不由评分文件名代替。

`commands/audit_release_batches.py --out-dir <目录>` 校验保存数据并输出逐文件批次与预算来源。默认目录为 experiment_results/release_inventory；相对路径以本独立目录为根。

`subset-routes` 的 `--matched-full` 是完整匹配路线，`--split-manifest` 提供训练索引，`--out` 为训练侧路线子集；三项都支持绝对路径与相对本目录的路径。负索引、重复索引、测试重叠及数量不符会报错。
