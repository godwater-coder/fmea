# FMEA 实验目录说明

本目录只保留两类正式实验：

- `对比实验`：按模型组织，用于比较不同行为边界的模型。
- `消融实验`：按数据集组织，用于比较 Full 与去除模块后的 Full-Mi。

当前目录已经按“实验类型 -> 模型或数据集 -> 具体运行”的方式整理，便于论文实验部分引用。

统一总表见 `实验/实验总表.md`。

## 1. 对比实验

目录：

```text
实验/对比实验/
```

对比实验按模型划分，目前包含两个模型组：

```text
实验/对比实验/LLM/
实验/对比实验/baseline/
```

### 1.1 LLM

`LLM` 表示不使用本文 KG-RAG 系统模块的本地大模型对照。当前保留两类运行方式：

- `表格上下文回答`：每题将完整标准化 CSV 表格内容随 prompt 提供给 `qwen2.5:7b`，不使用知识图谱、RAG、数据库查询、CSV 直答、确定性规则或证据裁决。
- `直接回答`：只根据题面由 `qwen2.5:7b` 直接回答，不提供图谱、RAG 或表格上下文。

现有结果：

```text
实验/对比实验/LLM/zenodo_floating_wind_fmea/表格上下文回答/
实验/对比实验/LLM/磷酸铁锂电池DFMEA/表格上下文回答/
实验/对比实验/LLM/磷酸铁锂电池DFMEA/直接回答/
```

### 1.2 Baseline

`Baseline` 表示固定的 legacy KG-RAG 对照模型。Baseline 不参与模块开关重构，用于说明传统 KG-RAG 路径在相同题集上的表现。

现有结果：

```text
实验/对比实验/baseline/zenodo_floating_wind_fmea/
实验/对比实验/baseline/磷酸铁锂电池DFMEA/
```

## 2. 消融实验

目录：

```text
实验/消融实验/
```

消融实验按数据集划分，目前包含两个数据集：

```text
实验/消融实验/zenodo_floating_wind_fmea/
实验/消融实验/磷酸铁锂电池DFMEA/
```

每个数据集目录下保存 Full、Full-Mi 和 `Full-SigmaMi_残差模型` 结果，用于检查去除全部已定义模块后是否接近 Baseline。

模块口径如下：

| 模块 | 含义 |
| --- | --- |
| M1 | CSV 直答模块 |
| M2 | 确定性规则问答模块 |
| M3 | QueryIR 与语义检索增强模块 |
| M4 | 证据检查与路由裁决模块 |

主要结果目录示例：

```text
实验/消融实验/zenodo_floating_wind_fmea/Full_全量模型/
实验/消融实验/zenodo_floating_wind_fmea/Full-M1_去除CSV直答模块/
实验/消融实验/zenodo_floating_wind_fmea/Full-M2_去除确定性规则问答模块/
实验/消融实验/zenodo_floating_wind_fmea/Full-M3_去除查询理解与检索增强模块/
实验/消融实验/zenodo_floating_wind_fmea/Full-M4_去除证据检查与路由裁决模块/

实验/消融实验/磷酸铁锂电池DFMEA/Full_全量模型/
实验/消融实验/磷酸铁锂电池DFMEA/Full-M1_去除CSV直答模块/
实验/消融实验/磷酸铁锂电池DFMEA/Full-M2_去除确定性规则问答模块/
实验/消融实验/磷酸铁锂电池DFMEA/Full-M3_去除查询理解与检索增强模块/
实验/消融实验/磷酸铁锂电池DFMEA/Full-M4_去除证据检查与路由裁决模块/
实验/消融实验/磷酸铁锂电池DFMEA/Full-SigmaMi_残差模型/
```

## 3. 模块专项实验

模块专项实验用于说明单个模块对应的现实问题是否被针对性解决，因此放在对应数据集的消融实验目录下：

```text
实验/消融实验/zenodo_floating_wind_fmea/模块专项实验/
实验/消融实验/磷酸铁锂电池DFMEA/模块专项实验/
```

这种放置方式的理由是：模块专项实验不是独立模型对比，而是服务于消融解释。它应当和 Full、Full-Mi 放在同一数据集目录下，方便按数据集查看“主评测 + 模块专项”的完整证据链。

## 4. 常用结果文件

每次正式运行一般包含以下文件：

```text
实验结果/模型回答.jsonl
实验结果/逐题明细.jsonl
实验结果/逐题明细.csv
实验结果/分类汇总.csv
实验结果/汇总指标.json
实验结果/使用题集.json
实验结果/实验报告.md
实验结果/运行日志.log
```

其中论文中优先引用 `汇总指标.json`、`分类汇总.csv` 和 `实验报告.md`；需要分析错题或路径时再查看 `逐题明细.csv/jsonl`。
