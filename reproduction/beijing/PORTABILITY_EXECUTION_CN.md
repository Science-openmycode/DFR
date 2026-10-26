# 单目录迁移修复：本轮执行计划

主机本机；工作目录为本交付目录。前两项只生成命令/检查迁移接口，不重新运行已完成的正式算法。对应README命令迁移由用户本轮明确授权，旧服务器命令和旧执行记录保留。

```powershell
.venv/Scripts/python.exe tools/prepare_portable_sweeps.py
```

下面检查搬到中文空格目录后，补充配置、已保存输入、命令解析与绘图数据绑定。不生成正式轨迹、不重新评价旧成绩。

```powershell
.venv/Scripts/python.exe tools/verify_portable_supplements.py --out validation/portable_supplements_20261024.json
```

新汇总入口的数值兼容性（只对原35份保存的标量汇总，不重新评分）：

```powershell
.venv/Scripts/python.exe -m pytest tests/test_portable_supplement_collection.py -q -p no:cacheprovider
```

新增补充实验说明的真实参数入口检查，不运行实验：

```powershell
.venv/Scripts/python.exe tools/audit_readme_commands.py --supplement SUPPLEMENT_COMMANDS_CN.md --out validation/portable_supplement_commands_20261024.json
```

仅补测上次迁移之后加入的K核心、六份公共划分与绘图依赖。禁止读取整个原工作区，迁移目录与Python环境除外；不重测408条旧范围。

```powershell
.venv/Scripts/python.exe "../便携验证 空格 20261024/tools/verify_portable_late.py" --forbid-workspace ../.. --allow-environment .venv --out "../便携验证 空格 20261024/late_result.json"
```

仅验证新增的原生模型目录解析与文档解释器拼写；不训练、不生成、不弱化原执行证据检查。

```powershell
.venv/Scripts/python.exe -m pytest tests/test_portable_native_paths.py -q -p no:cacheprovider
```
