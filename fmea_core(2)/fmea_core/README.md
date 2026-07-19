# fmea_core

这个目录用于承接 FMEA 核心逻辑的迁移入口，并提供一套可复用的统一范式，
作为后续所有 FMEA 数据导入、图谱建模、检索和问答的唯一基础格式。

## 1. 目标定位

当前仓库里的核心能力仍然位于 [code/kg_rag_core](../code/kg_rag_core)，
但为了便于后续维护和复用，已经把 FMEA 的对外入口收敛为统一包名：

```python
from fmea_core import KGRAGService
```

同时，新增了一套以“标准 FMEA 分析表”为基准的跨领域通用 FMEA 核心范式，用于支撑后续扩展。

## 2. 统一范式交付物

本次已提供以下结构化规范：

- 统一结构定义：[fmea_core/specs/fmea_core_schema.json](specs/fmea_core_schema.json)
- 原始字段到标准字段的映射规则：[fmea_core/specs/field_mapping_rules.yaml](specs/field_mapping_rules.yaml)
- 导入前标准化与归一化规则：[fmea_core/specs/normalization_rules.yaml](specs/normalization_rules.yaml)

## 3. 基于标准 FMEA 分析表的字段体系

第一版公共字段已对齐标准 FMEA 分析表中最稳定的列：

- item_process：项目/工序/对象
- function：功能
- failure_mode：失效模式
- failure_effect：失效后果
- severity：严重度
- failure_cause：失效原因
- occurrence：频度
- prevention_control / detection_control / current_control：现行控制
- detection：探测度
- rpn：风险优先数
- recommended_action：建议措施
- owner：责任人
- target_completion_date：目标完成日期
- action_taken：已采取措施
- revised_severity / revised_occurrence / revised_detection / revised_rpn：修订后评分
- status：状态
- source_table / source_record_id：来源追踪

## 4. 扩展字段机制

无法纳入公共字段但又具有业务价值的信息，统一放入受控扩展字段：

- 以 ext_ 或 ext. 前缀命名
- 支持字符串、数字、布尔、数组和对象类型
- 例如：ext_part_number、ext_environment、ext_test_method、ext_raw_value

这样可以避免统一范式过于僵硬，同时保证核心结构稳定。

## 5. 设计原则

- 先抽象共性，再容纳差异
- 公共字段保证跨领域通用
- 扩展字段保证业务可扩展
- 所有字段都能映射到统一命名
- 导入前先归一化，再入库

## 6. 后续使用建议

后续新增领域时，应优先遵循以下流程：

1. 先确认原始表字段是否能映射到公共字段
2. 不能映射的内容放入扩展字段
3. 按标准化规则清洗数据
4. 生成统一范式记录，再进入图谱/检索/问答链路

## 6. 统一导入脚本使用方式

现在已经提供了可直接运行的导入脚本：[fmea_core/normalize_fmea.py](normalize_fmea.py)。

### 6.1 转换 CSV/Excel 为统一范式

脚本支持标准 FMEA 分析表列名，包括：

- FMEA编号
- 产品
- 分析层级
- 项目/功能
- 潜在失效模式
- 潜在失效后果
- 严酷度(S)
- 潜在失效原因/机理
- 发生度(O)
- 现行预防控制
- 现行探测控制
- 可探测度(D)
- 风险优先数(RPN)
- 措施优先级(AP)
- 建议措施
- 措施状态
- 措施结果
- 备注

```bash
python3 fmea_core/normalize_fmea.py data/example_fmea.csv --output fmea_core/output/example_normalized.json --format json
```

### 6.2 输出结果

脚本会把原始 FMEA 表转换为统一字段结构，例如：

```json
{
  "record_id": "10",
  "item_process": "Wire harness routing",
  "failure_mode": ["Electrical short"],
  "failure_effect": ["Wires pinched"],
  "failure_cause": ["Incorrect routing"],
  "severity": 4.0,
  "occurrence": 5.0,
  "detection": 3.0,
  "rpn": 60.0
}
```

## 7. 迁移目标

- 保留现有 FMEA KG/RAG 逻辑不变
- 统一对外导入路径
- 后续可把业务代码逐步从旧包迁移到新的入口
- 为图谱 schema、检索链路和问答链路提供稳定的数据基础
