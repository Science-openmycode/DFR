# 小规模后续入口：从人工输入到任务、攻击和MTNet导出

在reproduction/beijing执行，先完成README环境安装。所有目录均从本页命令生成；已完成的步骤可以复用。人工时间与轨迹只用于程序检查，不能用于论文性能或攻击结论。

## 1. 输入、原生发布和表示转换

输入64条、每条21坐标，对应20条道路；768节点公共图含两跳边，384区域保留多个公共选择。划分51训练/13测试。DFR使用epsilon1.4。

```powershell
python tools/prepare_cli_fixture.py --out data/branch_cli_fixture --runtime data/fmm-runtime/Library/bin --records 64 --public-nodes 768 --branched --points 21 --with-artificial-times
python prepare_tstr_split.py --config data/branch_cli_fixture/native.json --out data/branch_cli_fixture/split --out-config data/branch_cli_fixture/ready.json
python synthesize_dfr.py --config data/branch_cli_fixture/ready.json --length-aware --out results/branch_cli/full
python synthesize_dfr_train.py --config data/branch_cli_fixture/ready.json --length-aware --out results/branch_cli/train
python tools/convert_native_node_pairs.py --routes results/branch_cli/full/seed_42_length/road_routes.pkl.gz --network data/branch_cli_fixture/network.shp --expected-slots 64 --out results/branch_cli/full_routes
python tools/convert_native_node_pairs.py --routes results/branch_cli/train/release/seed_42_length/road_routes.pkl.gz --network data/branch_cli_fixture/network.shp --expected-slots 51 --out results/branch_cli/train_routes
python tools/stage_native_saved_coordinates.py --routes results/branch_cli/train_routes/synthetic_routes.pkl.gz --network data/branch_cli_fixture/network.shp --edge-cache data/branch_cli_fixture/edge_cache.pkl.gz --native-source results/branch_cli/train/release/seed_42_length/road_routes.pkl.gz --for-tstr --out-dir results/branch_cli/train_view
python tools/prepare_cli_followups.py --config data/branch_cli_fixture/ready.json --out data/branch_followups --train-coordinates results/branch_cli/train_view/coordinates.pkl --train-lineage results/branch_cli/train/lineage.json
```

生成data/branch_cli_fixture、results/branch_cli/full、train、full_routes、train_view。原生道路只转换表示。

## 2. 隐私攻击与道路任务

```powershell
python prepare_attack_inputs.py --config data/branch_cli_fixture/ready.json --out data/branch_followups/attack --out-config data/branch_followups/attack_ready.json --releases data/branch_followups/releases.json
python experiments/privacy_attack.py --config data/branch_followups/attack_ready.json --batch branch_cli_attack
python evaluation/run_bound_ordered_attack.py --config data/branch_followups/ordered_attack.json --out results/branch_cli/ordered_attack
python evaluate.py --config data/branch_cli_fixture/ready.json --method MTR-DFR --router Origin --input results/branch_cli/full_routes/synthetic_routes.pkl.gz --out results/branch_cli/road_scores
python evaluate_road_tasks.py --config data/branch_cli_fixture/ready.json --method MTR-DFR --router Origin --input results/branch_cli/full_routes/synthetic_routes.pkl.gz --score-manifest results/branch_cli/road_scores/manifest.json --out results/branch_cli/road_tasks
python legacy/evaluation/run_physical_experiment.py --real-routes data/branch_cli_fixture/dataset/road_records.pkl.gz --synthetic-routes results/branch_cli/full_routes/synthetic_routes.pkl.gz --edge-cache data/branch_cli_fixture/metric_cache.pkl.gz --network data/branch_cli_fixture/network.shp --method MTR-DFR --sampling-label MTR-DFR --cap-per-stratum 20 --out-dir results/branch_cli/physical
```

成员攻击生成results/branch_cli_attack/privacy/results.csv；有序攻击生成results/branch_cli/ordered_attack下逐条件结果；道路与物理结构结果分别在road_scores、road_tasks、physical。小样本攻击不代表正式隐私证明或正式攻击强度。

## 3. K与预算入口

```powershell
python synthesize_k.py --config data/branch_cli_fixture/ready.json --length-aware --endpoint-partition data/branch_followups/partition24.json --out results/branch_cli/k24
python synthesize_dfr.py --config data/branch_followups/budget_0p2.json --length-aware --out results/branch_cli/budget_0p2
```

分别生成64槽的K24分支和epsilon0.2分支。完整论文扫描仍使用supplement/sweeps的原配置与五种子命令；本页不改变其设计。

## 4. MTNet作者格式与独立导出

```powershell
python prepare_mtnet_frozen.py --config data/branch_cli_fixture/ready.json --original-adapter-root vendor/mtnet --time-binding data/branch_cli_fixture/artificial_time_binding.json --raw-reference data/branch_cli_fixture/dataset/trajectories.pkl --out results/branch_cli/MTNet_prepared
python prepare_mtnet_deployment.py --prepared results/branch_cli/MTNet_prepared --original-root vendor/mtnet --out results/branch_cli/MTNet_deployment --archive results/branch_cli/MTNet_deployment.zip
```

生成MTNet_prepared和MTNet_deployment.zip。64条输入均满足原L20过滤；安装README的系统运行库及GPU依赖后，按原生基线文档运行训练脚本。导出成功不表示GPU训练已执行。

