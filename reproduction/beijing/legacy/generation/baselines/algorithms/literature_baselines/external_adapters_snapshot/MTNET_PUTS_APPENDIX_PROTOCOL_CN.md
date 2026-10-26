# MTNet、PUTS 与 MTR：附录比较的协议边界

本目录的比较不属于论文主表的共享协议 leaderboard。三者的输出对象和释放协议不同；本说明规定附录中可以、以及不可以作出的结论。

## MTNet-DP-SGD

MTNet 是条件路段序列生成器：生成函数接收起始路段和时间条件。条件生成器本身可以满足 DP，前提是该条件是公开常量、外部用户请求，或者已由独立 DP 机制发布。

下列做法不能直接称为无条件中央 DP 合成数据发布：对私有数据集的每条记录提取其起点/时间，再以这些私有条件生成一条并发布。条件集合本身是数据依赖输出；除非它已固定为公开协议或纳入隐私账本，否则 DP-SGD 对模型参数的保证不自动覆盖该集合。

因此，本附录的北京 MTNet 诊断采用固定的、数据无关的协议：

* 发布数固定为 17,123；
* 起始边从公开 OSM 路段索引均匀采样；
* 时间槽固定为 0；
* 使用本地 fixed-batch Algorithm-1 DP-SGD 实现和保守的 `(epsilon=1, delta=1e-5)` 会计；
* 不把这个实现称为作者超参数的数值复现。

这会故意移除真实轨迹起点需求的捷径，因而 OD 指标是需要检验而不是应被忽略的量。它也不意味着 MTNet 的原论文 DP 定义错误；它说明“条件生成评测”和“自由合成数据发布”必须分开报告。

## PUTS

原实现的 `TrajectorySynthesizer.precomputeMarkov` 显式构造
`tbR[maxStep+1, R, R]` 并计算 `T_k=T_{k-1}P`。令 `R` 为使用的有向路段数、`L` 为最大步数：

* 存储：`Theta((L+1) R^2)`；
* 稠密矩阵递推时间：`Theta(L R^3)`；
* 全对道路最短路径缓存还需 `Theta(R^2)` 存储。

北京全图中 `R=76,366`，若 `L=50`、float64，则仅 transition tensor 的下界为 `8 * 51 * R^2 = 2.38 TB`，还未计入矩阵乘临时空间和最短路径缓存。因此不能把稀疏化、按需 BFS 或道路分区后得到的北京结果称为原始 PUTS 的严格全城运行；那是新的工程适配。

附录仅报告 UCAR 原生规模诊断，同时保留一个明确标注为小网络的可视化。它说明 PUTS 可以输出沿路轨迹，但不支持把该结果外推为北京/波尔图规模的正式比较。

## 可审计产物

* MTNet 全量 release：`outputs/synthetic_releases/external_competitors/mtnet_dpsgd_public_seed.pkl`
* MTR 全量 release：`outputs/synthetic_releases/current_best/mtr_dp_gsrt.pkl`
* 基础指标：`outputs/external_competitors/mtnet_vs_mtr/full_metrics/`
* 路径系统入域指标：`outputs/external_competitors/mtnet_vs_mtr/downstream/`
* 全量 edge 指标：`outputs/external_competitors/mtnet_vs_mtr/edge_metrics_full/`
* 附录图：`outputs/external_competitors/figures/external_road_network_diagnostics.png`

运行完整 edge 评估：

```powershell
python pipeline/evaluate_external_road_comparators.py
```

该命令只读取已保存的合成 release 和公开 OSM；不训练模型，也不改动合成数据。
