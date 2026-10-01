# MTNet 官方源码审计

- 审计日期：2026-07-12。
- 官方 artifact：`https://github.com/wangyong01/MTNet_Code` 主分支。
- 官方归档 Git blob：`8b5bf05cce008d302b339e5783945b4130efdc89`，`20,487,130` bytes。
- 本地审计用 `MTNet.zip` 的 Git blob SHA-1 与官方完全一致。
- 官方归档包含普通 MTNet、demo 数据和预训练权重，但不含 DP-SGD 训练器、隐私会计器、裁剪阈值 `C` 或噪声倍率 `sigma`。
- 官方 demo 配置是 `BATCH_SIZE=8192`、`EPOCHS=3`、`USE_TGRAPH=True`；论文正文报告的是 `L=20`、最多 30 epochs、patience 5 与 `(epsilon,delta)=(1,10^-5)`。
- 本地旧目录的 `train.py`、`mtnet.py`、`util/config.py`、`util/dataloader.py` 哈希均与官方归档不一致，故不再作为严格复现的代码基线。
- 北京 L=20 迁移按论文“仅收集长度不超过 L 的轨迹”规则得到 1,101 条 FMM 路径，少于官方 demo 的 `B=8192`。迁移训练显式使用 `B=1101`，仅可称为 Algorithm-1-faithful transfer。
