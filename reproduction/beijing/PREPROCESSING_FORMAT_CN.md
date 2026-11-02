# 统一预处理输出格式

## 边界

统一原始入口为 `preprocess_dataset.py --config configs/datasets/<city>.raw.json`。北京GeoLife PLT与START Porto ZIP由各自适配器解析，经来源与道路审查后进入同一冻结格式，再由共同导出器生成下面的标准结构。配置负责城市差异，不需要修改Python代码；未接入的其它原始格式不能自动冒充已支持。

## 所有城市相同的目录

```text
dataset.json              城市资源配置，所有路径相对本文件
records.jsonl.gz          逐条标准记录，城市间字段完全相同
time_endpoints.csv        可用时提供，不伪造缺失时间
prepared/                已有算法使用的兼容视图，原文件字节不变
public/network.*         有向公共道路图及坐标系
public/metric_cache.pkl.gz
export_report.json       数量、可用能力、自动生成的文件校验信息
```

## 每条标准记录

| 字段 | 一致定义 |
|---|---|
| record_index | 冻结人口中的0起始连续编号 |
| source_index | 原始来源记录编号，不重新编号冒充原始来源 |
| split | train或test，完整沿用冻结划分 |
| coordinates | WGS84 `[latitude, longitude]` 数组 |
| road_ids | 公共图中的有向边编号序列，保持重复与顺序，不补路 |
| point_timestamps | 与坐标逐点对齐的已知时间；没有就为null，不插值填充 |
| start_ts/end_ts | 已知的来源起止UTC秒；没有就为null |

坐标来源与时间含义写在dataset.json：既有北京冻结道路数据是GPS观测投影到已匹配道路后的坐标，Porto是作者道路几何视图；两者使用相同字段，但不冒充原始GPS观测坐标。相同格式不代表凭空补齐缺失信息。道路编号只需在各自公共图内一致，不要求北京和Porto使用相同编号。投影在公共图及routing_crs中明确，不把投影米坐标塞入经纬度字段。

## 不得改变的内容

共同导出不重新匹配、不改变人口、不删除长轨迹、不去重复道路、不重新划分训练测试。未知道路等级不猜测；没有某方法必要能力时在该方法准备阶段明确报错。文件校验自动生成，用户不需要手工管理哈希。旧北京命令及原数据保持不动，prepared兼容视图服务于逐步迁移，不是第二次独立预处理。

北京兼容包的point_timestamps为null，但原PLT观测day-serial时刻已恢复到raw_metadata，不能据此声称源数据没有逐点时间；包内提供真实UTC端点。Porto保留START处理后的逐点UTC数组。共同结构允许明确的null，不插值制造观测。

公共路由资源、算法专用输入与训练属于后续步骤；数据包成功不代表这些实验已经完成。

## 已有真实数据验证

2026-10-29：Porto原始ZIP全量695083条（556066训练/139017测试）六阶段验收通过。

2026-10-30：北京原始18670个PLT全量重读，17123条来源坐标及观测时间全量一致；保留原审查15730条（12584训练/3146测试）。修复历史审查格式、迁址路径及投影末位漂移后，一键流程成功；独立严格比较证明新旧坐标、完整道路记录、来源及划分逐值完全相同。真实命令和失败修复记录见执行账本，运行方式见README。

同日Porto按README原句再次从原始ZIP全量完成，695083条标准记录逐条核验通过，两城record_keys集合与road-trajectory-record-v1一致，均真实退出0。当前实测与可复制命令统一以README为准。
