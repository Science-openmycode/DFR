# 小规模命令行检查：不生成论文成绩

先完成README的Python环境和DATA_CN中的FMM运行库安装，激活`.venv`，设置UTF-8。以下命令均在reproduction/beijing执行。输入是明确标记的人工小路网，不拿它代替北京实验。每条命令独立运行，失败时先看该条错误，不执行依赖它的后续步骤。

## 1. 输入准备

384个公共道路节点用于满足DFR原算法384区域的合法输入要求；DFR生成16条。统计M输入含51000个人工点，用来满足PrivTrace原代码的输入规模要求；各M输出16条。算法阈值、隐私预算不改。

```powershell
python tools/prepare_cli_fixture.py --out data/cli_fixture --runtime data/fmm-runtime/Library/bin
python prepare_tstr_split.py --config data/cli_fixture/native.json --out data/cli_fixture/split --out-config data/cli_fixture/split_ready.json
python prepare_ubodt.py --config data/cli_fixture/split_ready.json --out-dir data/cli_fixture/ubodt --out-config data/cli_fixture/ready.json --delta-m 1500 --threads 2
```

输出人工输入、公共图、train/test划分核验和小图UBODT；每个输出目录必须是新目录。

## 2. 四种统计M

```powershell
python synthesize.py --config data/cli_fixture/measurement.json --method SPRT --out results/cli_fixture/M/SPRT
python synthesize.py --config data/cli_fixture/measurement.json --method PrivTrace --out results/cli_fixture/M/PrivTrace
python synthesize.py --config data/cli_fixture/measurement.json --method DPTraj-PM --out results/cli_fixture/M/DPTraj-PM
python synthesize.py --config data/cli_fixture/measurement.json --method DPStd --out results/cli_fixture/M/DPStd
```

每条生成measurement.pkl、measurement_manifest.json和日志，不产生道路评分。失败输出不能拿去作图。

## 3. 同一份M输出选择公共R

```powershell
python route.py --config data/cli_fixture/ready.json --method SPRT --router Origin --input results/cli_fixture/M/SPRT --out results/cli_fixture/R/Origin
python route.py --config data/cli_fixture/ready.json --method SPRT --router Nearest --input results/cli_fixture/M/SPRT --out results/cli_fixture/R/Nearest
python route.py --config data/cli_fixture/ready.json --method SPRT --router FMM --input results/cli_fixture/M/SPRT --out results/cli_fixture/R/FMM
python route.py --config data/cli_fixture/ready.json --method SPRT --router STMatch --input results/cli_fixture/M/SPRT --out results/cli_fixture/R/STMatch
```

四条共享SPRT输出，不重新读取真实数据测量。Origin保留坐标；其余产生道路记录。MM2使用另一个已有公共网络，需要单独检查，不能把此小图和北京MM2二进制网络混用。

## 4. DFR原生生成和道路评分

```powershell
python synthesize_dfr.py --config data/cli_fixture/ready.json --length-aware --out results/cli_fixture/native/MTR-DFR
python synthesize_dfr_train.py --config data/cli_fixture/ready.json --length-aware --out results/cli_fixture/native_train/MTR-DFR
python evaluate.py --config data/cli_fixture/ready.json --method SPRT --router Nearest --input results/cli_fixture/R/Nearest/synthetic_routes.pkl.gz --out results/cli_fixture/scores/Nearest
python evaluate_coordinates.py --config data/cli_fixture/ready.json --method SPRT --router Origin --input results/cli_fixture/R/Origin/synthetic_coordinates.pkl --metric-protocol audit-v2 --out results/cli_fixture/scores/coordinates
```

DFR完整输出16槽、训练分支12槽。评分输出metrics.json及manifest。小样本数值只用于检查接口，不比较算法优劣。

## 5. 已有回归入口

```powershell
$env:DFR_TEST_RUNTIME="$PWD/data/fmm-runtime/Library/bin"
python -m pytest tests -q
```

这套测试还检查错误输入拒绝、空槽位、数据划分、命令与绘图数据接口。它不代替DPMM、MTNet、MM2实际生成、完整TSTR、攻击、消融和敏感性入口的单独运行；这些项目在服务器测试记录中分别列状态，未完成不能写为全部通过。

## 6. DPMM实际加速生成检查

`--records 64`准备64条人工轨迹，以满足现有验证入口的60条对照要求；不降低原对照数量。先运行验证，再把刚生成的validation.json交给生成器，用户不用填写历史数据哈希。

```powershell
python tools/prepare_cli_fixture.py --out data/dpmm_cli_fixture --runtime data/fmm-runtime/Library/bin --records 64
python validate_dpmm_dataset.py --config data/dpmm_cli_fixture/native.json --adapter vendor/dpmm/original/check/run_dpmm_official_beijing.py --optimizer vendor/dpmm/fast_dpmm_paths.py --out results/dpmm_cli_validation --records 60 --exact-records 60
python synthesize_dpmm.py --config data/dpmm_cli_fixture/native.json --adapter vendor/dpmm/original/check/run_dpmm_official_beijing.py --optimizer vendor/dpmm/fast_dpmm_paths.py --validation results/dpmm_cli_validation/validation.json --workers 2 --split full --out results/dpmm_cli_generation
```

预期先输出60条逐轨迹比较，再生成dpmm.pkl、dpmm.json、new_dataset_execution.json。输出数以DPMM实际发布情况为准，检查其保留的输入索引；不能把未发布记录补造为轨迹。
