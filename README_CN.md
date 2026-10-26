# MTR-DFR

MTR-DFR 从差分隐私测量中生成道路级合成轨迹。仓库包含算法、基线实现、评估工具、已保存的合成数据集和作图代码。

[English](README.md) · [逐步实验说明](reproduction/beijing/README_CN.md) · [数据下载与预处理](reproduction/beijing/DATA_CN.md)

## 从这里开始

当前北京实验放在 [`reproduction/beijing`](reproduction/beijing)。数据准备、合成、路由、评估和作图分别执行，按照[实验说明](reproduction/beijing/README_CN.md)的顺序运行即可。

先安装 [Git LFS](https://git-lfs.com/)，再下载仓库与数据资源：

```powershell
git lfs install
git clone https://github.com/Science-openmycode/DFR.git
cd DFR
git lfs pull
cd reproduction/beijing
```

随仓库提供的 FMM/STMatch 程序用于 Windows x64。实验使用 Python 3.13.9 和说明中指定的依赖；MTNet 训练还需要 NVIDIA GPU。

## 实验顺序

1. 安装运行环境。
2. 下载 GeoLife，解析坐标和时间戳，并在公共道路图上预处理轨迹。
3. 运行 SPRT、PrivTrace、DPTraj-PM、DPStd 的统计合成，或运行 MTR-DFR、DPMM、MTNet 的原生道路合成。
4. 为统计方法的同一份输出选择 Origin、Nearest、FMM、STMatch 或 MM2-MDP。
5. 计算统计保真度、道路覆盖、路线选择和下游任务指标，再运行组件消融、分辨率与隐私预算实验。
6. 用评估生成的结果文件作图。

[逐步说明](reproduction/beijing/README_CN.md)列出各阶段的命令入口和产物。新建数据批次时，预处理流程会按用户的输入和输出位置生成独立命令文档。

## 数据与结果

原始 GeoLife 轨迹从 Microsoft 下载，具体步骤见[数据说明](reproduction/beijing/DATA_CN.md)。北京公共道路图通过 Git LFS 随仓库提供。

当前道路级北京参考语料包含 15,730 条轨迹。全集实验合成同样大小的数据集，与参考语料比较。严格 TSTR 单独采用 12,584/3,146 的训练/测试划分：合成器只用真实训练集，预测器在合成训练集上训练，最后在真实测试集上评估。

早期坐标级实验使用 17,123 条轨迹，数据与图件分别保留在根目录的 `datasets/` 和 `experiment_results/`。当前道路级流程有独立的批次配置和结果目录。

外部数据、道路资源和基线的许可与引用说明放在各自目录中。
