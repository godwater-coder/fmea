# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re

import pandas as pd

from synonyms import CSV_COLUMN_SYNONYMS


@dataclass(frozen=True)
class SchemaField:
    name: str
    source_headers: tuple[str, ...]
    entity: str
    property_name: str
    dtype: str
    required: bool = False
    description: str = ""


PROJECT_SCHEMA_VERSION = "fmea_core_v1"

PROJECT_SCHEMA_FIELDS: tuple[SchemaField, ...] = (
    SchemaField("FmeaID", ("FMEA编号",), "FailureMode", "FmeaID", "string"),
    SchemaField("Product", ("产品",), "FailureMode", "Product", "string"),
    SchemaField("AnalysisLevel", ("分析层级",), "FailureMode", "AnalysisLevel", "string"),
    SchemaField("ProcessStep", ("项目/功能", "设计项目", "过程步骤", "工序"), "ProcessStep", "ProcessStep", "string", True),
    SchemaField("FailureMode", ("潜在失效模式", "潜在的失效模式"), "FailureMode", "FailureMode", "string", True),
    SchemaField("FailureEffect", ("潜在失效后果", "潜在的失效后果"), "FailureEffect", "FailureEffect", "string"),
    SchemaField("FailureCause", ("潜在失效原因/机理", "潜在的失效原因/机理", "潜在失效原因"), "FailureCause", "FailureCause", "string"),
    SchemaField("S", ("严酷度(S)", "严重度"), "FailureMode", "S", "number"),
    SchemaField("O", ("发生度(O)", "发生度", "频度数"), "FailureMode", "O", "number"),
    SchemaField("D", ("可探测度(D)", "探测度", "探测度数"), "FailureMode", "D", "number"),
    SchemaField("RPN", ("风险优先数(RPN)", "RPN"), "FailureMode", "RPN", "number"),
    SchemaField("ActionPriority", ("措施优先级(AP)", "AP"), "FailureMode", "ActionPriority", "string"),
    SchemaField("PreventControl", ("现行预防控制", "现行预防性设计控制"), "FailureMode", "PreventControl", "string"),
    SchemaField("DetectionMeasure", ("现行探测控制", "现行探测性设计控制", "现行探测性控制"), "FailureMode", "DetectionMeasure", "string"),
    SchemaField("RecommendedAction", ("建议措施", "临时采取的措施"), "FailureMode", "RecommendedAction", "string"),
    SchemaField("ActionStatus", ("措施状态",), "FailureMode", "ActionStatus", "string"),
    SchemaField("ActionResult", ("措施结果",), "FailureMode", "ActionResult", "string"),
    SchemaField("Remark", ("备注",), "FailureMode", "Remark", "string"),
    SchemaField("Domain", (), "FailureMode", "Domain", "string"),
    SchemaField("DatasetID", (), "FailureMode", "DatasetID", "string"),
    SchemaField("ProjectID", (), "FailureMode", "ProjectID", "string"),
    SchemaField("SchemaVersion", (), "FailureMode", "SchemaVersion", "string"),
    SchemaField("SourceFile", (), "FailureMode", "SourceFile", "string"),
    SchemaField("SourceRowNo", (), "FailureMode", "SourceRowNo", "number"),
    SchemaField("ImportBatchID", (), "FailureMode", "ImportBatchID", "string"),
)


SCHEMA_FIELD_INDEX: dict[str, SchemaField] = {field.name: field for field in PROJECT_SCHEMA_FIELDS}


def _norm_col(name: object) -> str:
    return re.sub(r"\s+", "", str(name or "")).strip()


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _safe_number(value: Any) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except Exception:
        return None
    return int(number) if number.is_integer() else number


def rename_standard_headers(df: pd.DataFrame) -> pd.DataFrame:
    renamed = df.copy()
    renamed.columns = [str(c).strip() for c in renamed.columns]

    mapping: dict[str, str] = {}
    existing = set(renamed.columns)
    for original in list(renamed.columns):
        target = CSV_COLUMN_SYNONYMS.get(_norm_col(original))
        if not target or target == original or target in existing:
            continue
        mapping[original] = target

    if mapping:
        renamed = renamed.rename(columns=mapping)
    return renamed


def normalize_to_project_schema(
    df: pd.DataFrame,
    *,
    source_file: str = "",
    dataset_id: str = "default",
    project_id: str = "default",
    domain: str = "fmea",
    import_batch_id: str = "",
    schema_version: str = PROJECT_SCHEMA_VERSION,
) -> pd.DataFrame:
    rows = rename_standard_headers(df)
    out = pd.DataFrame(index=rows.index)

    for field in PROJECT_SCHEMA_FIELDS:
        if field.source_headers:
            value = None
            for header in field.source_headers:
                if header in rows.columns:
                    value = rows[header]
                    break
            if value is not None:
                out[field.name] = value

    if "ProcessStep" in rows.columns and "ProcessStep" not in out.columns:
        out["ProcessStep"] = rows["ProcessStep"]
    if "FailureMode" in rows.columns and "FailureMode" not in out.columns:
        out["FailureMode"] = rows["FailureMode"]
    if "FailureEffect" in rows.columns and "FailureEffect" not in out.columns:
        out["FailureEffect"] = rows["FailureEffect"]
    if "FailureCause" in rows.columns and "FailureCause" not in out.columns:
        out["FailureCause"] = rows["FailureCause"]
    if "PreventControl" in rows.columns and "PreventControl" not in out.columns:
        out["PreventControl"] = rows["PreventControl"]
    if "DetectionMeasure" in rows.columns and "DetectionMeasure" not in out.columns:
        out["DetectionMeasure"] = rows["DetectionMeasure"]
    if "RecommendedAction" in rows.columns and "RecommendedAction" not in out.columns:
        out["RecommendedAction"] = rows["RecommendedAction"]
    if "S" in rows.columns and "S" not in out.columns:
        out["S"] = rows["S"]
    if "O" in rows.columns and "O" not in out.columns:
        out["O"] = rows["O"]
    if "D" in rows.columns and "D" not in out.columns:
        out["D"] = rows["D"]
    if "RPN" in rows.columns and "RPN" not in out.columns:
        out["RPN"] = rows["RPN"]

    if "ProcessStep" in out.columns:
        out["ProcessStep"] = out["ProcessStep"].ffill()

    for text_col in (
        "FmeaID",
        "Product",
        "AnalysisLevel",
        "ProcessStep",
        "FailureMode",
        "FailureEffect",
        "FailureCause",
        "ActionPriority",
        "PreventControl",
        "DetectionMeasure",
        "RecommendedAction",
        "ActionStatus",
        "ActionResult",
        "Remark",
    ):
        if text_col in out.columns:
            out[text_col] = out[text_col].map(_safe_text)

    for num_col in ("S", "O", "D", "RPN"):
        if num_col in out.columns:
            out[num_col] = out[num_col].map(_safe_number)

    if "RPN" not in out.columns:
        out["RPN"] = None
    if {"S", "O", "D"}.issubset(set(out.columns)):
        computed = []
        for s_val, o_val, d_val, rpn_val in zip(out["S"].tolist(), out["O"].tolist(), out["D"].tolist(), out["RPN"].tolist()):
            if rpn_val is not None:
                computed.append(rpn_val)
                continue
            if s_val is None or o_val is None or d_val is None:
                computed.append(None)
                continue
            computed.append(int(float(s_val) * float(o_val) * float(d_val)))
        out["RPN"] = computed

    source_name = Path(source_file).name if source_file else ""
    out["Domain"] = domain
    out["DatasetID"] = dataset_id
    out["ProjectID"] = project_id
    out["SchemaVersion"] = schema_version
    out["SourceFile"] = source_name
    out["SourceRowNo"] = [int(i) + 2 for i in range(len(out.index))]
    out["ImportBatchID"] = import_batch_id

    # 兼容当前查询代码中的历史字段名，直到查询层完全切换。
    out["TempMeasure"] = out.get("RecommendedAction")

    return out
