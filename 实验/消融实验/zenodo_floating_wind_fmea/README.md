# FMEA KG-RAG 消融模型说明

本目录用于固定论文消融实验的模型变体定义。所有变体共用主代码 `code/kg_rag_core`，通过环境变量关闭指定模块，避免复制代码后产生版本漂移。

## 实验组

| 目录 | 说明 |
|---|---|
| `Full_全量模型` | 当前完整 FMEA KG-RAG 模型。 |
| `Full-ΣMi_残差模型` | 关闭 M1-M4，用于验证 `Full-ΣMi` 是否接近固定 Baseline。 |
| `Full-M1_去除CSV直答模块` | 关闭 `CSV直答`，验证明确编号/字段查询的直答能力。 |
| `Full-M2_去除确定性规则问答模块` | 关闭 `确定性规则问答`，验证结构化规则推理与聚合问答能力。 |
| `Full-M3_去除查询理解与检索增强模块` | 关闭 `Query IR 查询意图解析 + 语义检索预处理与排序增强 + 口语化/模糊问题优先 RAG 路由`，验证自然语言理解与检索增强能力。 |
| `Full-M4_去除证据检查与路由裁决模块` | 关闭证据检查、路由裁决与 KG chunk 抽取式回答，验证图谱证据约束对稳定性和幻觉控制的作用。 |

## 模块定义

- `M1`：CSV直答模块。
- `M2`：确定性规则问答模块。
- `M3`：QueryIR 查询意图解析、语义检索预处理与排序增强、口语化/模糊问题优先 RAG 路由。
- `M4`：证据检查、路由裁决与 KG chunk 抽取式回答模块。

`Baseline` 为固定 legacy 对比模型，不参与本目录开关重构。正式消融前先跑 `Full-ΣMi_残差模型`；若其准确率明显高于 Baseline，则说明模块拆分仍未覆盖 Full 的主要能力，应先重划模块。

## 待测指标

- 完全准确率
- 平均部分准确率
- 平均耗时
- 上下文精确率
- 证据召回率
- 幻觉率
- 多跳路径覆盖率

## 模块专项实验

模块专项题集与结果单独保存在当前数据集目录下的 `模块专项实验/`，避免覆盖原有 1500 题实验。

- 题集：`DATA/zenodo_floating_wind_fmea/module_eval/special_all_400_questions.jsonl`
- M1-M4：每类 100 题
- 题集标签版：`DATA/zenodo_floating_wind_fmea/module_eval/all_module_eval_1900_questions.jsonl`
- 四类专项子集：`DATA/zenodo_floating_wind_fmea/module_eval/special/`
- 汇总报告：`实验/消融实验/zenodo_floating_wind_fmea/模块专项实验/消融实验/zenodo_floating_wind_fmea/模块专项实验总报告.md`

专项实验同时运行 `Baseline`、`Full` 和 `Full-M1` 到 `Full-M4`，以同一套 400 题比较总体指标与目标模块分组指标。
