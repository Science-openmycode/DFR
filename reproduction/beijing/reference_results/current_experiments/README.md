# 当前北京实验汇总（2026-11-11）

这些文件是已完成实验的汇总，不包含真实逐条轨迹、逐轨迹区域成员、训练检查点、真实任务答案明细、服务器路径或凭据。数据规模15730，方法为DFR、PrivTrace、AdaTrace、DPTraj-PM、MTNet及MTNet＋DP-OD。原始GeoLife数据请按主README向官方获取，不能把汇总文件当作训练输入。

| 文件 | 内容 |
|---|---|
| mr/framework_matrix_transposed.png、pdf | ε=1的11指标×19列矩阵，209格；24格不适用，适用项无缺失 |
| mr/cells.json | 原评分值、状态及可用的结果来源哈希；只删除本机路径，不改分值 |
| budget/budget_current.png、pdf | 六方法×七档预算×11指标，共462点，无缺失 |
| budget/plot_data.csv | 各方法的均值、n、样本标准差及种子，DFR每档5种子，其余每档一次 |
| mr/compare_github.png、budget/compare_github.png | 发布前逐图核对：左为前一GitHub图，右为本批图 |
| manifest.json | 人口、范围、原输入哈希及公开文件哈希 |

MR的坐标方法分别使用Origin、Nearest、FMM、STMatch、标准MM2；原生方法只保留自身道路输出。预算实验的坐标方法使用轻量MM2，三种原生方法不重新匹配。DPTraj-PM的网格参数见主README，显示名不带超参数。不同方法的隐私单位和协议说明保留在各入口及主指南，不能把研究基线合称同一已认证隐私发布。

图中代表路线采用固定十区域、每区最多5条的既定任务。它与旧GitHub单区域图不同；其余DFR七档10指标共70个共同点的均值和SD逐值相同。MR新旧预算/方法列不同，不把同名格自动当成同一实验。红框与零/不适用处理保持既定规则。

在主README指定环境中，工作目录为reproduction/beijing，可以仅从公开汇总重画（输出目录必须尚不存在）：

```powershell
python plotting/render_mr.py --data reference_results/current_experiments/mr/cells.json --epsilon 1 --slots 15730 --out results/public_mr_redraw
python plotting/render_budget_comparison.py --data reference_results/current_experiments/budget/plot_data.csv --out results/public_budget_redraw --representative-label "Coverage (10 regions, 5 routes)"
```

这些命令只重画，不能替代生成/路由/评分验收。完整实验按根README执行。K六档×五种子复用既有验收结果与原K章节，不在本次复制或重算。
