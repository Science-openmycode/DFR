# MTR-DFR 复现事实表

本目录是 MTR-DFR 的独立复现目录，发布到 GitHub 私有仓库 `MTR-DFR`。目录只包含 DFR、四个统计式 baseline、统一评估器和已经保存的合成结果。

| 项目 | 当前目录中的内容 | 从头复现入口 |
|---|---|---|
| MTR-DFR 主方法 | `generation/mtr_dfr/`；已保存五个种子的 DP transcript、道路路线和协议 manifest | `python commands/reproduce.py generate-main ...` |
| 四个统计基线 | SPRT、PrivTrace、DPTraj-PM、DPStd 的适配器源码和已保存合成发布 | `python commands/reproduce.py generate-baselines ...` |
| MTR 框架提升 | 固定测量下的原生发布与公共道路路由比较 | `run-framework` |
| 隐私接口攻击 | DOMIAS、GDA-MIA、起点链接和路线链接结果 | `run-privacy` |
| 完整道路效用 | RoadYield、DirValid、DemandFid、BTF、RC/Edge/Turn/Family CPC、IoU、BranchCPC、ExitAcc | `run-profile` |
| M×R 矩阵 | 同一测量配对不同路由器，比较 Native、FMM、STMatch 与 DFR 路由 | `run-mr` |
| 算法级消融 | endpoint demand、complete-family measurement、匹配路由的组合消融 | `run-ablation` |
| 严格 TSTR | 只从训练划分生成，在未参与生成的测试轨迹上评估下游任务 | `run-tstr` |
| 逐轨迹结构 | Backbone、闭合回访和重复道路访问诊断 | `run-physical` |
| 已生成图片 | `experiment_results/published_figures/` 与 `regenerated_figures/` | `python commands/reproduce.py plot ...` |

## 已随目录保存的事实

- 北京冻结真实输入：17,123 条轨迹；严格 TSTR 划分为 13,698 条训练轨迹和 3,425 条测试轨迹。
- MTR-DFR 五个研究种子：`20260719`–`20260723`。
- DFR 的私有测量预算与协议记录在每个发布目录的 `protocol.json` 和 `manifests/` 中；路由阶段只读取 DP transcript、公共道路图、固定输出槽位和新随机性。
- 冻结报告中的 MTR-DFR 代表值来自 `experiment_results/frozen/`；重新运行命令会把新结果写入用户指定目录，不覆盖冻结结果。
- Porto 和 San Francisco 的命令、bbox、公共 OSM 缓存和输入转换见 `docs/CROSS_CITY_COMMANDS_CN.md`。这些城市不复用北京道路缓存。

## 复现顺序

1. 安装 `requirements-lock.txt`，按 `README_CN.md` 配置 FMM/STMatch 运行库。
2. 准备真实轨迹和同城公共道路参考。
3. 生成 MTR-DFR 与四个统计基线。
4. 依次运行 `run-framework`、`run-privacy`、`run-profile`、`run-mr`、`run-ablation`、`run-tstr` 和 `run-physical`。
5. 用 `plot -- --figure ... --data-root <本轮结果目录>` 生成对应图片。

每个命令的参数、输出文件和跨数据集替换方法写在 `docs/COMMAND_PARAMETERS_CN.md`；按论文顺序的完整命令写在 `README_CN.md`。
