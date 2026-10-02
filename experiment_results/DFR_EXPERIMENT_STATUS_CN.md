# DFR 实验状态

| 实验 | 当前状态 | 位置 |
|---|---|---|
| 北京主 DFR 生成与统一评估 | 已完成 | `experiment_results/executed_reference/` 与主 README |
| 分辨率敏感性 (K=2,4,8,16,32,64) | 已完成 | `experiment_results/sensitivity/` |
| 隐私预算敏感性 (arepsilon=0.2,0.4,0.7,1.0,1.4,2.0,3.0) | 已完成 | `experiment_results/sensitivity/` |
| DFR 算法级四臂消融 | 已完成 | `experiment_results/ablation/` |
| Porto/SF DFR 全指标复现 | 当前版本未完成 | 公共发布目录没有对应 DFR 道路图与 ordered edge cache，不能把旧 GSRT/评估侧 STMatch 结果冒充 DFR 原生结果 |
| Oldenburg DFR 500,000 条扩展 | 当前版本未完成 | 公共发布目录没有 Oldenburg 的 DFR 道路图与 edge cache；隔离目录中的旧结果不并入 DFR 冻结结果 |

新增敏感性和消融结果均来自 GitHub 当前代码和固定北京输入。缺少公共道路资产的城市不会被写成已经完成的 DFR 实验。
