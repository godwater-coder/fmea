# -*- coding: utf-8 -*-

"""集中维护 KG-RAG FMEA 服务使用的同义词与别名映射。

本模块刻意将映射保持为简单数据结构（dict/list/str），
以便主流程代码保持清晰可读。

注意：这里不是通用 NLP 同义词引擎，
所有映射均为项目定制的规则化归一配置。
"""

from __future__ import annotations

# --------------------------------------------------------------------------------------
# CSV 列名同义词（中文/变体列名 -> 内部标准字段名）
# --------------------------------------------------------------------------------------

# 查找前应先对键做归一化（例如去除空白与换行）。
CSV_COLUMN_SYNONYMS: dict[str, str] = {
    # 工序/项目
    "设计项目": "ProcessStep",
    "过程步骤": "ProcessStep",
    "工序": "ProcessStep",
    # 失效相关
    "潜在的失效模式": "FailureMode",
    "潜在失效模式": "FailureMode",
    "潜在的失效后果": "FailureEffect",
    "潜在失效后果": "FailureEffect",
    "潜在的失效原因/机理": "FailureCause",
    "潜在失效原因/机理": "FailureCause",
    "潜在的失效原因": "FailureCause",
    "潜在失效原因": "FailureCause",
    # 评分
    "严重度": "S",
    "频度数": "O",
    "发生度": "O",
    "探测度数": "D",
    "探测度": "D",
    "RPN": "RPN",
    # 控制/措施
    "现行探测性设计控制": "DetectionMeasure",
    "现行探测性控制": "DetectionMeasure",
    # 临时措施更贴近“改进措施”语义，作为 FailureMeasure
    "临时采取的措施": "FailureMeasure",
    # 预防性控制（在建图时会合并进 FailureMeasure，同时也保留专用字段）
    "现行预防性设计控制": "PreventControl",
}

# --------------------------------------------------------------------------------------
# 问题文本同义词
# --------------------------------------------------------------------------------------

# 指标（S/O/D/RPN）关键词映射，供 deterministic 分支匹配使用。
# 这里只存数据；具体匹配策略由 `kg_rag.py` 决定（子串或正则）。
METRIC_SYNONYMS: dict[str, dict[str, object]] = {
    "S": {
        "keywords": ["严重度"],
        "regex": r"\\bS\\b",
    },
    "O": {
        "keywords": ["频度", "发生度"],
        "regex": r"\\bO\\b",
    },
    "D": {
        "keywords": ["探测度", "检测度"],
        "regex": r"\\bD\\b",
    },
    "RPN": {
        "keywords": ["RPN"],
        "regex": None,
    },
}

# ProcessStep 表达清洗：去除常见后缀。
PROCESS_STEP_SUFFIX_PATTERN: str = r"(设计项目|过程步骤|工序|项目)$"

# 识别问句模式时使用的意图短语别名。
INTENT_SYNONYMS: dict[str, list[str]] = {
    "double_contains": ["同时包含", "同时含有", "同时包括", "同时包含了"],
    "detect_use": ["用于探测", "被用于探测", "用于检测"],
    "max": ["风险最高", "最高", "最大"],
    "min": ["风险最低", "最低", "最小"],
}

# 失效原因语义分类别名/关键词，用于原因类查询。
# 适配 deterministic 分支中的“哪些失效原因属于/涉及/指向 ...”问法。
CAUSE_SEMANTIC_SYNONYMS: dict[str, dict[str, list[str]]] = {
    "设计缺陷": {
        "aliases": ["设计问题", "设计不良", "结构设计问题", "软件设计缺陷"],
        "keywords": [
            "设计不合理", "风道设计不合理", "封合胶量不足", "焊接缺陷",
            "密封结构破坏", "达不到要求", "不阻燃", "密封不严",
        ],
    },
    "外部环境因素": {
        "aliases": ["环境因素", "环境影响", "工况因素", "外界环境"],
        "keywords": [
            "环境温度", "通风方式", "风扇固定", "功率过高", "灰尘", "进水", "潮湿", "凝露",
        ],
    },
    "用户操作不当": {
        "aliases": ["误操作", "操作不当", "违规操作", "使用不当"],
        "keywords": [
            "违规操作", "安装不规范", "负载未断开", "未压紧", "连接错误", "未明确区分正负极",
            "使用电流高于额定电流",
        ],
    },
    "外部干扰": {
        "aliases": ["电磁干扰", "环境干扰", "外力干扰", "外部扰动"],
        "keywords": [
            "电磁干扰", "干扰", "外力损伤", "碰撞", "震动", "挤压",
        ],
    },
    "算法质量问题": {
        "aliases": ["算法编写错误", "算法错误", "鲁棒性过差", "软件鲁棒性差", "逻辑错误", "程序缺陷"],
        "keywords": [
            "SOC算法", "算法不合理", "BMS 控制系统", "BMS控制系统", "软件", "程序", "控制系统",
        ],
    },
}

# 统一导出对象，便于调试与外部查看。
SYNONYMS: dict[str, object] = {
    "csv_columns": CSV_COLUMN_SYNONYMS,
    "metric": METRIC_SYNONYMS,
    "process_step_suffix_pattern": PROCESS_STEP_SUFFIX_PATTERN,
    "intent": INTENT_SYNONYMS,
    "cause_semantic": CAUSE_SEMANTIC_SYNONYMS,
}
