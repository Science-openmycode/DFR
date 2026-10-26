# 实验运行说明

在 `dfr_reproducible_20261009` 文件夹打开终端。每项实验运行一个 Python 文件，数据路径和参数集中写在 [configs/beijing.yaml](../configs/beijing.yaml) 中。算法使用原有实现，入口负责依次运行命令、保存日志和耗时。

## 1. 环境和配置

```powershell
python -m pip install -r requirements-lock.txt
```

本机可使用 `E:/anconda/python.exe` 替代下面命令中的 `python`。

配置文件采用 JSON 语法（也是 YAML 的子集），不需要额外安装 YAML 解析器。所有相对路径以 `dfr_reproducible_20261009` 为基准，不以终端所在目录为基准。

换机器时，将数据和原有实现一起转移，修改配置中的 `paths`：

- `legacy`：原有 DFR 与基线实现目录，当前是 `../../tmp_dfr_remote_verify_20261002_new`。该目录是运行依赖，不是联网下载入口。
- `prepared`：统一预处理数据目录，包含 `trajectories.pkl` 和 `bbox.json`。
- `real`、`real_routes`：真实坐标全集与对应匹配道路输入。
- `network`、`osm`：公共道路网络和 OSM 缓存。Shapefile 的 `.shp/.dbf/.shx/.prj` 等文件一起保留。
- `edge_cache`：与公共网络编号对齐的评估缓存；`source_cache`：DFR 原有输入编号缓存，两者不要互换。
- `fmm`、`stmatch`、`runtime`、`ubodt`：匹配程序、运行库和 FMM 查找表。当前配置绑定 Windows 可执行文件，Linux 上须替换为相应版本。
- `train`、`test`、`split_audit`：独立的训练/测试数据及划分记录。
- `members`、`nonmembers`、`reference`、`attack_manifest`：已有攻击数据划分。
- `releases`：已有 train-only 合成坐标文件及对应 `lineage`。更换数据时须同时更换这些记录，不能混用另一批结果。
- `output`：新实验结果保存目录。

主要参数：`epsilon=1.4` 是本次生成总预算；`seed` 是合成随机种子；`evaluation_seed` 是评估种子；`slots=17123` 是显式指定的输出大小，不从私有输入自动推断；`bbox` 顺序为最小纬度、最大纬度、最小经度、最大经度；`threads` 控制数值库线程数，不等于并发实验数。`population=accepted-road-subset` 沿用当前 DFR 消融的成功匹配输入口径，不是全集消融。

## 2. 统计基线 M×R 实验

```powershell
python experiments/main.py
```

依次为 SPRT、PrivTrace、DPTraj-PM、DPStd 生成坐标发布；每份 M 输出分别接 Origin、Nearest、FMM、STMatch；随后运行评估。默认共 4 次生成、16 次路由/原生复制、16 次评估。R 复用同一份 M 输出，不重新测量真实数据。

生成文件位于 `data_results/simple_runs/corrected_20261013/measurements/<M>/`；路由文件和评估结果位于 `routes/<M>/<R>/`，其中 `metrics/metrics.json` 保存评分。SPRT、PrivTrace、DPStd 已改接冻结的正确实现，旧错误批次退出当前项目。Origin 输出坐标，不能将其当成原生道路发布。

只跑一个 M：

```powershell
python experiments/main.py --method SPRT
```

在另一台机器上跑第四个 M：

```powershell
python experiments/main.py --method DPStd
```

MM2 单独最后执行：

```powershell
python experiments/main.py --only-router MM2-MDP
```

该命令复用同批次已完成的 M，没有完成时会先生成。当前入口只编排这四个统计 M；DFR 的原生完整生成在下一节的 `full` 组中执行。

## 3. DFR 算法级消融

```powershell
python experiments/ablation.py
```

实际重新生成四组：删除端点测量、仅端点测量、删除长度测量、完整 DFR。调用原有消融评估器，保留原有预算与样本口径，产生 `ablation/arms/` 下的四份道路数据、`ablation/results.csv` 和 `ablation/manifest.json`。

完成后作图：

```powershell
python experiments/plot.py --experiment ablation
```

生成 `figures/ablation/05_ablation.png` 和 PDF。该命令调用原有绘图函数，只读本批次 CSV，不使用旧冻结分数补缺。

## 4. 严格 TSTR 下游实验

```powershell
python experiments/tstr.py
```

此入口读取配置中**已有的五份 train-only 合成数据**，重新执行下游模型训练和评分，不重新合成数据。五份是四个统计基线的 Origin 和 DFR 原生发布的确定性坐标表示，不是 FMM/STMatch 的 TSTR 组合。真实训练和合成训练使用同一个未见真实测试集；脚本强制校验合成来源与独立划分。

产生 `tstr/results.csv`、`tstr/manifest.json`，以及 `raw_generic/`、`raw_road/` 中的原始任务结果。

```powershell
python experiments/plot.py --experiment tstr
```

生成 `figures/tstr/06_strict_tstr.png` 和 PDF，沿用原绘图函数及指标选择。

## 5. 隐私攻击实验

```powershell
python experiments/privacy_attack.py
```

读取同一批已登记的 train-only 合成数据，重新运行 Population-linkage 与 GDA-MIA 两种成员推断攻击，输出 `privacy/results.csv` 和 `privacy/manifest.json`。这是经验攻击实验，不能代替差分隐私证明，也不是相邻世界的统一攻击实验。

```powershell
python experiments/plot.py --experiment privacy_attack
```

生成 `figures/privacy/03_privacy_attacks.png` 和 PDF。

## 6. 按顺序运行上面四项实验

```powershell
python reproduce.py
```

执行顺序为统计 M×R、DFR 消融、TSTR 重测、成员推断攻击重测；不包含 MM2，不自动作图。作图分别使用各节的命令。

换配置、换批次、查看命令的参数通用：

```powershell
python experiments/ablation.py --config configs/beijing.yaml --batch simple_002
python experiments/main.py --dry-run
```

`--config` 指定配置；`--batch` 指定新输出子目录；`--dry-run` 只展示将要执行的底层命令，不生成实验数据。`--help` 列出入口参数。

每一步会实时显示进度和实际耗时，详细命令、输入/输出哈希和运行记录写入 `logs/`。同一批次已完成且哈希一致的步骤会跳过；失败步骤不会假装完成，也不做算法内部断点恢复。参数或输入变化时使用新批次；旧结果不覆盖。
