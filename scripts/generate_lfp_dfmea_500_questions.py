# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

import pandas as pd
import sys


ROOT = Path(__file__).resolve().parents[1]
CODE_DIR = ROOT / "code"
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

FMEA_SCHEMA_PATH = CODE_DIR / "kg_rag_core" / "fmea_schema.py"
spec = importlib.util.spec_from_file_location("fmea_schema", FMEA_SCHEMA_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"无法加载 {FMEA_SCHEMA_PATH}")
fmea_schema = importlib.util.module_from_spec(spec)
sys.modules["fmea_schema"] = fmea_schema
spec.loader.exec_module(fmea_schema)
rename_standard_headers = fmea_schema.rename_standard_headers


DEFAULT_CSV = Path("data/磷酸铁锂电池FMECA分析表20250416105822.csv")
DEFAULT_OUT = Path("DATA/磷酸铁锂电池Dfmea分析/eval/lfp_dfmea_500_questions.jsonl")


def _s(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _n(value: Any) -> float | None:
    text = _s(value)
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def _df(csv_path: Path) -> pd.DataFrame:
    df = rename_standard_headers(pd.read_csv(csv_path)).fillna("")
    if "ProcessStep" in df.columns:
        df["ProcessStep"] = df["ProcessStep"].ffill()
    return df


def _label_for_question(kind: str) -> tuple[str, str, str]:
    if kind.startswith("cause"):
        return "故障原因诊断类", "故障原因诊断类", "fault_cause_diagnosis"
    if kind.startswith("action"):
        return "故障措施推荐类", "故障措施推荐类", "fault_action_recommendation"
    return "风险影响评估类", "风险影响评估类", "risk_impact_assessment"


def _module_hint(kind: str) -> tuple[str, str, str]:
    if kind in {
        "cause_code",
        "effect_code",
        "action_code",
        "rpn_code",
        "s_code",
        "o_code",
        "d_code",
    }:
        return "M1", "M1_编号直答", "CSV直答"
    if kind in {"project_avg_rpn", "project_top_mode", "project_top_effect", "risk_stats", "risk_project", "project_compare"}:
        return "M2", "M2_规则推理", "规则推理"
    if kind in {
        "cause_colloquial",
        "effect_colloquial",
        "action_colloquial",
        "risk_colloquial",
        "cause_mode",
        "effect_mode",
        "action_mode",
        "rpn_mode",
        "risk_mode_code",
        "risk_mode_project",
    }:
        return "M3", "M3_查询理解与语义检索增强", "口语化/模糊检索"
    if kind in {"cause_bool", "risk_bool", "mode_project_bool", "project_bool"}:
        return "M4", "M4_证据裁决", "证据裁决"
    if kind in {"cause_multi", "action_multi", "risk_multi"}:
        return "M3", "M3_查询理解与语义检索增强", "多跳/语义检索"
    return "M3", "M3_查询理解与语义检索增强", "默认路由"


def _make_item(
    *,
    question: str,
    kind: str,
    row_index: int,
    expected_terms: list[str] | None = None,
    expected_numbers: list[float] | None = None,
    reference_answer: str = "",
    expected_fields: list[str] | None = None,
    expected_bool: bool | None = None,
    difficulty: str = "medium",
    style_tags: list[str] | None = None,
) -> dict[str, Any]:
    category_cn, category_tag, primary_label = _label_for_question(kind)
    module, module_name, module_note = _module_hint(kind)
    labels = [category_tag, *(_ for _ in (style_tags or []) if _), module.lower()]
    item = {
        "scenario": "battery_dfmea_main",
        "情景类别": category_cn,
        "kind": kind,
        "题型": kind,
        "标签": category_tag,
        "difficulty": difficulty,
        "question": question,
        "expected_terms": expected_terms or [],
        "expected_numbers": expected_numbers or [],
        "expected_fields": expected_fields or [],
        "参考答案": reference_answer,
        "row_index": row_index,
        "labels": labels,
        "primary_label": primary_label,
        "labeling_method": "battery_dfmea_generator",
        "label_notes": "磷酸铁锂电池 DFMEA 主评测题。",
        "module_label": module,
        "module_label_name": module_name,
        "module_label_note": module_note,
        "source_domain": "磷酸铁锂电池DFMEA",
    }
    if expected_bool is not None:
        item["expected_bool"] = bool(expected_bool)
    return item


def _row_questions(row: pd.Series, idx: int) -> list[dict[str, Any]]:
    code = _s(row.get("FmeaID"))
    project = _s(row.get("ProcessStep"))
    mode = _s(row.get("FailureMode"))
    effect = _s(row.get("FailureEffect"))
    cause = _s(row.get("FailureCause"))
    action = _s(row.get("RecommendedAction")) or _s(row.get("TempMeasure"))
    prevent = _s(row.get("PreventControl"))
    detect = _s(row.get("DetectionMeasure"))
    s_val = _n(row.get("S"))
    o_val = _n(row.get("O"))
    d_val = _n(row.get("D"))
    rpn = _n(row.get("RPN"))

    items: list[dict[str, Any]] = []

    # 故障原因诊断类
    items.extend(
        [
            _make_item(
                question=f"FMEA编号{code}对应的潜在失效原因/机理是什么？",
                kind="cause_code",
                row_index=idx,
                expected_terms=[cause],
                reference_answer=cause,
                difficulty="easy",
                style_tags=["seq_anchor", "direct_lookup"],
            ),
            _make_item(
                question=f"失效模式“{mode}”对应的潜在失效原因/机理是什么？",
                kind="cause_noid",
                row_index=idx,
                expected_terms=[cause],
                reference_answer=cause,
                difficulty="easy",
                style_tags=["mode_anchor", "direct_lookup"],
            ),
            _make_item(
                question=f"在项目/功能“{project}”里，失效模式“{mode}”的原因讲白一点是什么？",
                kind="cause_colloquial",
                row_index=idx,
                expected_terms=[cause],
                reference_answer=cause,
                difficulty="medium",
                style_tags=["colloquial", "fault_site"],
            ),
            _make_item(
                question=f"FMEA编号{code}这条的后果是“{effect}”，那原因是什么？",
                kind="cause_multi",
                row_index=idx,
                expected_terms=[cause],
                reference_answer=cause,
                difficulty="hard",
                style_tags=["multi_hop", "effect_to_cause"],
            ),
            _make_item(
                question=f"FMEA编号{code}对应的原因是否包含“{cause}”？",
                kind="cause_bool",
                row_index=idx,
                expected_fields=["是/否判断"],
                reference_answer="是",
                expected_bool=True,
                difficulty="medium",
                style_tags=["boolean", "evidence_judgement"],
            ),
            _make_item(
                question=f"失效模式“{mode}”的原因讲白一点是啥？",
                kind="cause_plain",
                row_index=idx,
                expected_terms=[cause],
                reference_answer=cause,
                difficulty="medium",
                style_tags=["colloquial", "field_expression"],
            ),
        ]
    )

    # 故障措施推荐类
    items.extend(
        [
            _make_item(
                question=f"FMEA编号{code}对应的建议措施是什么？",
                kind="action_code",
                row_index=idx,
                expected_terms=[action],
                reference_answer=action,
                difficulty="easy",
                style_tags=["seq_anchor", "direct_lookup"],
            ),
            _make_item(
                question=f"失效模式“{mode}”对应的建议措施是什么？",
                kind="action_noid",
                row_index=idx,
                expected_terms=[action],
                reference_answer=action,
                difficulty="easy",
                style_tags=["mode_anchor", "direct_lookup"],
            ),
            _make_item(
                question=f"在项目/功能“{project}”里碰到失效模式“{mode}”，该怎么处理？",
                kind="action_colloquial",
                row_index=idx,
                expected_terms=[action],
                reference_answer=action,
                difficulty="medium",
                style_tags=["colloquial", "field_expression"],
            ),
            _make_item(
                question=f"FMEA编号{code}这条如果再出现，建议措施是什么？",
                kind="action_multi",
                row_index=idx,
                expected_terms=[action],
                reference_answer=action,
                difficulty="hard",
                style_tags=["multi_hop", "controls_to_action"],
            ),
            _make_item(
                question=f"FMEA编号{code}对应的现行预防控制、现行探测控制和建议措施分别是什么？",
                kind="action_combo",
                row_index=idx,
                expected_terms=[prevent, detect, action],
                reference_answer=f"现行预防控制：{prevent}；现行探测控制：{detect}；建议措施：{action}",
                difficulty="hard",
                style_tags=["multi_hop", "evidence_judgement"],
            ),
            _make_item(
                question=f"失效模式“{mode}”要怎么处理，直接说措施。",
                kind="action_plain",
                row_index=idx,
                expected_terms=[action],
                reference_answer=action,
                difficulty="medium",
                style_tags=["colloquial", "field_expression"],
            ),
        ]
    )

    # 风险影响评估类
    items.extend(
        [
            _make_item(
                question=f"FMEA编号{code}对应的潜在失效后果是什么？S、O、D、RPN分别是多少？",
                kind="risk_code",
                row_index=idx,
                expected_terms=[effect],
                expected_numbers=[x for x in (s_val, o_val, d_val, rpn) if x is not None],
                reference_answer=f"后果：{effect}；S={s_val}；O={o_val}；D={d_val}；RPN={rpn}",
                expected_fields=["潜在失效后果", "S", "O", "D", "RPN"],
                difficulty="easy",
                style_tags=["seq_anchor", "risk_metric"],
            ),
            _make_item(
                question=f"失效模式“{mode}”最后会造成什么后果，RPN是多少？",
                kind="risk_noid",
                row_index=idx,
                expected_terms=[effect],
                expected_numbers=[x for x in (rpn,) if x is not None],
                reference_answer=f"后果：{effect}；RPN={rpn}",
                expected_fields=["潜在失效后果", "RPN"],
                difficulty="easy",
                style_tags=["no_id_anchor", "risk_metric"],
            ),
            _make_item(
                question=f"在项目/功能“{project}”里，失效模式“{mode}”最后会影响到什么？",
                kind="risk_colloquial",
                row_index=idx,
                expected_terms=[effect],
                reference_answer=effect,
                difficulty="medium",
                style_tags=["colloquial", "field_expression"],
            ),
            _make_item(
                question=f"FMEA编号{code}对应的S、O、D和RPN分别是多少？",
                kind="risk_stats",
                row_index=idx,
                expected_numbers=[x for x in (s_val, o_val, d_val, rpn) if x is not None],
                reference_answer=f"S={s_val}；O={o_val}；D={d_val}；RPN={rpn}",
                expected_fields=["S", "O", "D", "RPN"],
                difficulty="hard",
                style_tags=["multi_hop", "numeric_reasoning"],
            ),
            _make_item(
                question=f"FMEA编号{code}对应的失效后果是否为“{effect}”？",
                kind="risk_bool",
                row_index=idx,
                expected_fields=["是/否判断"],
                reference_answer="是",
                expected_bool=True,
                difficulty="medium",
                style_tags=["boolean", "evidence_judgement"],
            ),
            _make_item(
                question=f"FMEA编号{code}对应的后果和RPN分别是什么？",
                kind="risk_multi",
                row_index=idx,
                expected_terms=[effect],
                expected_numbers=[x for x in (rpn,) if x is not None],
                reference_answer=f"后果：{effect}；RPN={rpn}",
                expected_fields=["潜在失效后果", "RPN"],
                difficulty="hard",
                style_tags=["multi_hop", "field_expression"],
            ),
        ]
    )

    return items


def _csv_direct_row_questions(row: pd.Series, idx: int) -> list[dict[str, Any]]:
    code = _s(row.get("FmeaID"))
    project = _s(row.get("ProcessStep"))
    mode = _s(row.get("FailureMode"))
    effect = _s(row.get("FailureEffect"))
    cause = _s(row.get("FailureCause"))
    action = _s(row.get("RecommendedAction")) or _s(row.get("TempMeasure"))
    prevent = _s(row.get("PreventControl"))
    detect = _s(row.get("DetectionMeasure"))
    s_val = _n(row.get("S"))
    o_val = _n(row.get("O"))
    d_val = _n(row.get("D"))
    rpn = _n(row.get("RPN"))
    controls = [x for x in (prevent, detect) if x]
    if not controls:
        controls = ["未记录"]

    return [
        _make_item(
            question=f"FMEA编号“{code}”对应的失效模式是什么？",
            kind="risk_code_direct_mode",
            row_index=idx,
            expected_terms=[mode],
            reference_answer=mode,
            expected_fields=["FailureMode"],
            difficulty="easy",
            style_tags=["csv_direct", "seq_anchor"],
        ),
        _make_item(
            question=f"FMEA编号“{code}”这条的潜在失效原因/机理是什么？",
            kind="cause_code_direct",
            row_index=idx,
            expected_terms=[cause],
            reference_answer=cause,
            expected_fields=["FailureCause"],
            difficulty="easy",
            style_tags=["csv_direct", "seq_anchor"],
        ),
        _make_item(
            question=f"FMEA编号“{code}”这条的潜在失效后果是什么？",
            kind="risk_code_direct_effect",
            row_index=idx,
            expected_terms=[effect],
            reference_answer=effect,
            expected_fields=["FailureEffect"],
            difficulty="easy",
            style_tags=["csv_direct", "seq_anchor"],
        ),
        _make_item(
            question=f"FMEA编号“{code}”这条的建议措施是什么？",
            kind="action_code_direct",
            row_index=idx,
            expected_terms=[action],
            reference_answer=action,
            expected_fields=["RecommendedAction"],
            difficulty="easy",
            style_tags=["csv_direct", "seq_anchor"],
        ),
        _make_item(
            question=f"FMEA编号“{code}”这条的现行预防控制和现行探测控制分别是什么？",
            kind="action_code_direct_controls",
            row_index=idx,
            expected_terms=controls,
            reference_answer=f"现行预防控制：{prevent or '未记录'}；现行探测控制：{detect or '未记录'}",
            expected_fields=["PreventControl", "DetectionMeasure"],
            difficulty="easy",
            style_tags=["csv_direct", "seq_anchor"],
        ),
        _make_item(
            question=f"FMEA编号“{code}”这条的RPN是多少？",
            kind="risk_code_direct_rpn",
            row_index=idx,
            expected_numbers=[rpn] if rpn is not None else [],
            reference_answer=f"RPN={rpn}",
            expected_fields=["RPN"],
            difficulty="easy",
            style_tags=["csv_direct", "seq_anchor"],
        ),
        _make_item(
            question=f"FMEA编号“{code}”这条的严酷度S是多少？",
            kind="risk_code_direct_s",
            row_index=idx,
            expected_numbers=[s_val] if s_val is not None else [],
            reference_answer=f"S={s_val}",
            expected_fields=["S"],
            difficulty="easy",
            style_tags=["csv_direct", "seq_anchor"],
        ),
        _make_item(
            question=f"FMEA编号“{code}”这条的发生度O是多少？",
            kind="risk_code_direct_o",
            row_index=idx,
            expected_numbers=[o_val] if o_val is not None else [],
            reference_answer=f"O={o_val}",
            expected_fields=["O"],
            difficulty="easy",
            style_tags=["csv_direct", "seq_anchor"],
        ),
        _make_item(
            question=f"FMEA编号“{code}”这条的可探测度D是多少？",
            kind="risk_code_direct_d",
            row_index=idx,
            expected_numbers=[d_val] if d_val is not None else [],
            reference_answer=f"D={d_val}",
            expected_fields=["D"],
            difficulty="easy",
            style_tags=["csv_direct", "seq_anchor"],
        ),
        _make_item(
            question=f"FMEA编号“{code}”这条的S、O、D、RPN分别是多少？",
            kind="risk_code_direct_sod_rpn",
            row_index=idx,
            expected_numbers=[x for x in (s_val, o_val, d_val, rpn) if x is not None],
            reference_answer=f"S={s_val}；O={o_val}；D={d_val}；RPN={rpn}",
            expected_fields=["S", "O", "D", "RPN"],
            difficulty="easy",
            style_tags=["csv_direct", "seq_anchor"],
        ),
        _make_item(
            question=f"失效模式“{mode}”对应的FMEA编号是什么？",
            kind="risk_mode_direct_code",
            row_index=idx,
            expected_terms=[code],
            reference_answer=code,
            expected_fields=["FmeaID"],
            difficulty="easy",
            style_tags=["csv_direct", "mode_anchor"],
        ),
        _make_item(
            question=f"失效模式“{mode}”的潜在失效原因/机理是什么？",
            kind="cause_mode_direct",
            row_index=idx,
            expected_terms=[cause],
            reference_answer=cause,
            expected_fields=["FailureCause"],
            difficulty="easy",
            style_tags=["csv_direct", "mode_anchor"],
        ),
        _make_item(
            question=f"失效模式“{mode}”的潜在失效后果是什么？",
            kind="risk_mode_direct_effect",
            row_index=idx,
            expected_terms=[effect],
            reference_answer=effect,
            expected_fields=["FailureEffect"],
            difficulty="easy",
            style_tags=["csv_direct", "mode_anchor"],
        ),
        _make_item(
            question=f"针对失效模式“{mode}”，建议措施是什么？",
            kind="action_mode_direct",
            row_index=idx,
            expected_terms=[action],
            reference_answer=action,
            expected_fields=["RecommendedAction"],
            difficulty="easy",
            style_tags=["csv_direct", "mode_anchor"],
        ),
        _make_item(
            question=f"针对失效模式“{mode}”，现行预防控制和现行探测控制分别是什么？",
            kind="action_mode_direct_controls",
            row_index=idx,
            expected_terms=controls,
            reference_answer=f"现行预防控制：{prevent or '未记录'}；现行探测控制：{detect or '未记录'}",
            expected_fields=["PreventControl", "DetectionMeasure"],
            difficulty="easy",
            style_tags=["csv_direct", "mode_anchor"],
        ),
        _make_item(
            question=f"失效模式“{mode}”的RPN是多少？",
            kind="risk_mode_direct_rpn",
            row_index=idx,
            expected_numbers=[rpn] if rpn is not None else [],
            reference_answer=f"RPN={rpn}",
            expected_fields=["RPN"],
            difficulty="easy",
            style_tags=["csv_direct", "mode_anchor"],
        ),
        _make_item(
            question=f"失效模式“{mode}”的严酷度S是多少？",
            kind="risk_mode_direct_s",
            row_index=idx,
            expected_numbers=[s_val] if s_val is not None else [],
            reference_answer=f"S={s_val}",
            expected_fields=["S"],
            difficulty="easy",
            style_tags=["csv_direct", "mode_anchor"],
        ),
        _make_item(
            question=f"失效模式“{mode}”的发生度O是多少？",
            kind="risk_mode_direct_o",
            row_index=idx,
            expected_numbers=[o_val] if o_val is not None else [],
            reference_answer=f"O={o_val}",
            expected_fields=["O"],
            difficulty="easy",
            style_tags=["csv_direct", "mode_anchor"],
        ),
        _make_item(
            question=f"失效模式“{mode}”的可探测度D是多少？",
            kind="risk_mode_direct_d",
            row_index=idx,
            expected_numbers=[d_val] if d_val is not None else [],
            reference_answer=f"D={d_val}",
            expected_fields=["D"],
            difficulty="easy",
            style_tags=["csv_direct", "mode_anchor"],
        ),
        _make_item(
            question=f"失效模式“{mode}”属于哪个项目/功能？",
            kind="risk_mode_direct_project",
            row_index=idx,
            expected_terms=[project],
            reference_answer=project,
            expected_fields=["ProcessStep"],
            difficulty="easy",
            style_tags=["csv_direct", "mode_anchor"],
        ),
    ]


def _project_questions(df: pd.DataFrame) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    groups = list(df.groupby("ProcessStep", sort=False))
    for idx, (project, sub) in enumerate(groups):
        project = _s(project)
        if not project:
            continue
        sub = sub.copy()
        rpn_values = pd.to_numeric(sub["RPN"], errors="coerce")
        top_row = sub.loc[rpn_values.idxmax()] if len(sub) and rpn_values.notna().any() else sub.iloc[0]
        low_row = sub.loc[rpn_values.idxmin()] if len(sub) and rpn_values.notna().any() else sub.iloc[0]
        top_mode = _s(top_row.get("FailureMode"))
        top_rpn = _n(top_row.get("RPN"))
        low_mode = _s(low_row.get("FailureMode"))
        avg_rpn = float(rpn_values.mean()) if rpn_values.notna().any() else None
        avg_s = float(pd.to_numeric(sub["S"], errors="coerce").mean()) if pd.to_numeric(sub["S"], errors="coerce").notna().any() else None

        items.extend(
            [
                _make_item(
                    question=f"项目/功能“{project}”里RPN最高的失效模式是什么？",
                    kind="risk_project",
                    row_index=int(top_row.name) if top_row.name is not None else idx,
                    expected_terms=[top_mode],
                    expected_numbers=[top_rpn] if top_rpn is not None else [],
                    reference_answer=f"最高RPN失效模式：{top_mode}；RPN={top_rpn}",
                    difficulty="hard",
                    style_tags=["project_scope", "numeric_reasoning"],
                ),
                _make_item(
                    question=f"项目/功能“{project}”的平均RPN是多少？",
                    kind="risk_project",
                    row_index=int(top_row.name) if top_row.name is not None else idx,
                    expected_numbers=[avg_rpn] if avg_rpn is not None else [],
                    reference_answer=f"平均RPN={avg_rpn:.2f}" if avg_rpn is not None else "",
                    difficulty="medium",
                    style_tags=["project_scope", "numeric_reasoning"],
                ),
                _make_item(
                    question=f"项目/功能“{project}”里RPN最高的那条，它的后果和原因分别是什么？",
                    kind="cause_multi",
                    row_index=int(top_row.name) if top_row.name is not None else idx,
                    expected_terms=[_s(top_row.get("FailureCause"))],
                    reference_answer=_s(top_row.get("FailureCause")),
                    difficulty="hard",
                    style_tags=["project_scope", "multi_hop"],
                ),
                _make_item(
                    question=f"项目/功能“{project}”的平均严重度S是多少？",
                    kind="risk_project",
                    row_index=int(top_row.name) if top_row.name is not None else idx,
                    expected_numbers=[avg_s] if avg_s is not None else [],
                    reference_answer=f"平均S={avg_s:.2f}" if avg_s is not None else "",
                    difficulty="medium",
                    style_tags=["project_scope", "numeric_reasoning"],
                ),
                _make_item(
                    question=f"这份表里是否包含项目/功能“{project}”？",
                    kind="project_bool",
                row_index=int(top_row.name) if top_row.name is not None else idx,
                expected_fields=["是/否判断"],
                reference_answer="是",
                expected_bool=True,
                    difficulty="medium",
                    style_tags=["project_scope", "boolean"],
                ),
            ]
        )
    return items


def _global_questions(df: pd.DataFrame) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if df.empty:
        return items
    rpn_values = pd.to_numeric(df["RPN"], errors="coerce")
    avg_rpn = float(rpn_values.mean()) if rpn_values.notna().any() else None
    max_rpn_row = df.loc[rpn_values.idxmax()] if rpn_values.notna().any() else df.iloc[0]
    min_rpn_row = df.loc[rpn_values.idxmin()] if rpn_values.notna().any() else df.iloc[0]
    all_projects = [p for p in df["ProcessStep"].dropna().map(_s).tolist() if p]
    unique_projects = list(dict.fromkeys(all_projects))
    project_stats: list[tuple[str, float]] = []
    project_max_stats: list[tuple[str, float]] = []
    for project in unique_projects:
        sub = df[df["ProcessStep"].map(_s) == project]
        prpn = pd.to_numeric(sub["RPN"], errors="coerce")
        if prpn.notna().any():
            project_stats.append((project, float(prpn.mean())))
            project_max_stats.append((project, float(prpn.max())))
    top_avg_project = max(project_stats, key=lambda x: x[1])[0] if project_stats else (unique_projects[0] if unique_projects else "")
    top_max_project = max(project_max_stats, key=lambda x: x[1])[0] if project_max_stats else (unique_projects[0] if unique_projects else "")

    items.extend(
        [
            _make_item(
                question="这份电池DFMEA里RPN最高的失效模式是什么？",
                kind="risk_project",
                row_index=int(max_rpn_row.name) if max_rpn_row.name is not None else 0,
                expected_terms=[_s(max_rpn_row.get("FailureMode"))],
                expected_numbers=[_n(max_rpn_row.get("RPN"))] if _n(max_rpn_row.get("RPN")) is not None else [],
                reference_answer=f"{_s(max_rpn_row.get('FailureMode'))}；RPN={_n(max_rpn_row.get('RPN'))}",
                difficulty="hard",
                style_tags=["global_scope", "numeric_reasoning"],
            ),
            _make_item(
                question="这份表里平均RPN是多少？",
                kind="risk_project",
                row_index=int(max_rpn_row.name) if max_rpn_row.name is not None else 0,
                expected_numbers=[avg_rpn] if avg_rpn is not None else [],
                reference_answer=f"平均RPN={avg_rpn:.2f}" if avg_rpn is not None else "",
                difficulty="medium",
                style_tags=["global_scope", "numeric_reasoning"],
            ),
            _make_item(
                question="这张表里RPN最高的那条失效后果是什么？",
                kind="risk_colloquial",
                row_index=int(max_rpn_row.name) if max_rpn_row.name is not None else 0,
                expected_terms=[_s(max_rpn_row.get("FailureEffect"))],
                reference_answer=_s(max_rpn_row.get("FailureEffect")),
                difficulty="medium",
                style_tags=["global_scope", "colloquial"],
            ),
            _make_item(
                question="这份表里是否出现过后果为“安全事故”的失效模式？",
                kind="risk_bool",
                row_index=0,
                expected_fields=["是/否判断"],
                reference_answer="是" if any("安全事故" in _s(v) for v in df["FailureEffect"].tolist()) else "否",
                expected_bool=any("安全事故" in _s(v) for v in df["FailureEffect"].tolist()),
                difficulty="easy",
                style_tags=["global_scope", "boolean"],
            ),
            _make_item(
                question="这份表里是否存在需要优先处理的高风险项目/功能？",
                kind="project_bool",
                row_index=0,
                expected_fields=["是/否判断"],
                reference_answer="是",
                expected_bool=True,
                difficulty="medium",
                style_tags=["global_scope", "boolean"],
            ),
            _make_item(
                question="哪一个项目/功能的平均RPN最高？",
                kind="project_compare",
                row_index=0,
                expected_terms=[top_avg_project] if top_avg_project else [],
                reference_answer=top_avg_project,
                difficulty="hard",
                style_tags=["global_scope", "multi_project_compare"],
            ),
            _make_item(
                question="哪一个项目/功能的最高RPN最大？",
                kind="project_compare",
                row_index=0,
                expected_terms=[top_max_project] if top_max_project else [],
                reference_answer=top_max_project,
                difficulty="hard",
                style_tags=["global_scope", "multi_project_compare"],
            ),
            _make_item(
                question="这张表里是否存在后果为“安全事故”且RPN不低的失效模式？",
                kind="risk_bool",
                row_index=0,
                expected_fields=["是/否判断"],
                reference_answer="是",
                expected_bool=any(
                    ("安全事故" in _s(effect) and (_n(rpn) is not None and _n(rpn) >= 90))
                    for effect, rpn in zip(df["FailureEffect"].tolist(), df["RPN"].tolist())
                ),
                difficulty="hard",
                style_tags=["global_scope", "multi_hop"],
            ),
            _make_item(
                question="这份表里RPN最低的失效模式是什么？RPN是多少？",
                kind="risk_project",
                row_index=int(min_rpn_row.name) if min_rpn_row.name is not None else 0,
                expected_terms=[_s(min_rpn_row.get("FailureMode"))],
                expected_numbers=[_n(min_rpn_row.get("RPN"))] if _n(min_rpn_row.get("RPN")) is not None else [],
                reference_answer=f"{_s(min_rpn_row.get('FailureMode'))}；RPN={_n(min_rpn_row.get('RPN'))}",
                difficulty="medium",
                style_tags=["global_scope", "numeric_reasoning"],
            ),
            _make_item(
                question="这份表里平均严重度S是多少？",
                kind="risk_project",
                row_index=0,
                expected_numbers=[float(pd.to_numeric(df["S"], errors="coerce").mean())],
                reference_answer=f"平均S={float(pd.to_numeric(df['S'], errors='coerce').mean()):.2f}",
                difficulty="medium",
                style_tags=["global_scope", "numeric_reasoning"],
            ),
        ]
    )
    return items


def _balanced_row_questions(row: pd.Series, idx: int) -> list[dict[str, Any]]:
    code = _s(row.get("FmeaID"))
    project = _s(row.get("ProcessStep"))
    mode = _s(row.get("FailureMode"))
    effect = _s(row.get("FailureEffect"))
    cause = _s(row.get("FailureCause"))
    action = _s(row.get("RecommendedAction")) or _s(row.get("TempMeasure"))
    s_val = _n(row.get("S"))
    o_val = _n(row.get("O"))
    d_val = _n(row.get("D"))
    rpn = _n(row.get("RPN"))

    items: list[dict[str, Any]] = []
    add = items.append

    add(
        _make_item(
            question=f"FMEA编号“{code}”这条的潜在失效原因/机理是什么？",
            kind="cause_code",
            row_index=idx,
            expected_terms=[cause],
            reference_answer=cause,
            difficulty="easy",
            style_tags=["seq_anchor", "direct_lookup"],
        )
    )
    add(
        _make_item(
            question=f"FMEA编号“{code}”这条的潜在失效后果是什么？",
            kind="effect_code",
            row_index=idx,
            expected_terms=[effect],
            reference_answer=effect,
            difficulty="easy",
            style_tags=["seq_anchor", "direct_lookup"],
        )
    )
    add(
        _make_item(
            question=f"FMEA编号“{code}”这条的RPN是多少？",
            kind="rpn_code",
            row_index=idx,
            expected_numbers=[rpn] if rpn is not None else [],
            reference_answer=f"RPN={rpn}",
            expected_fields=["RPN"],
            difficulty="easy",
            style_tags=["seq_anchor", "numeric_answer"],
        )
    )
    add(
        _make_item(
            question=f"FMEA编号“{code}”这条的S是多少？",
            kind="s_code",
            row_index=idx,
            expected_numbers=[s_val] if s_val is not None else [],
            reference_answer=f"S={s_val}",
            expected_fields=["S"],
            difficulty="easy",
            style_tags=["seq_anchor", "numeric_answer"],
        )
    )
    add(
        _make_item(
            question=f"FMEA编号“{code}”这条的O是多少？",
            kind="o_code",
            row_index=idx,
            expected_numbers=[o_val] if o_val is not None else [],
            reference_answer=f"O={o_val}",
            expected_fields=["O"],
            difficulty="easy",
            style_tags=["seq_anchor", "numeric_answer"],
        )
    )
    add(
        _make_item(
            question=f"FMEA编号“{code}”这条的D是多少？",
            kind="d_code",
            row_index=idx,
            expected_numbers=[d_val] if d_val is not None else [],
            reference_answer=f"D={d_val}",
            expected_fields=["D"],
            difficulty="easy",
            style_tags=["seq_anchor", "numeric_answer"],
        )
    )

    if action:
        add(
            _make_item(
                question=f"FMEA编号“{code}”这条的建议措施是什么？",
                kind="action_code",
                row_index=idx,
                expected_terms=[action],
                reference_answer=action,
                expected_fields=["RecommendedAction"],
                difficulty="easy",
                style_tags=["seq_anchor", "direct_lookup"],
            )
        )

    add(
        _make_item(
            question=f"失效模式“{mode}”对应的潜在失效原因/机理是什么？",
            kind="cause_mode",
            row_index=idx,
            expected_terms=[cause],
            reference_answer=cause,
            difficulty="easy",
            style_tags=["mode_anchor", "natural_language"],
        )
    )
    add(
        _make_item(
            question=f"失效模式“{mode}”对应的潜在失效后果是什么？",
            kind="effect_mode",
            row_index=idx,
            expected_terms=[effect],
            reference_answer=effect,
            difficulty="easy",
            style_tags=["mode_anchor", "natural_language"],
        )
    )
    add(
        _make_item(
            question=f"失效模式“{mode}”的RPN是多少？",
            kind="rpn_mode",
            row_index=idx,
            expected_numbers=[rpn] if rpn is not None else [],
            reference_answer=f"RPN={rpn}",
            expected_fields=["RPN"],
            difficulty="easy",
            style_tags=["mode_anchor", "numeric_answer"],
        )
    )
    if action:
        add(
            _make_item(
                question=f"失效模式“{mode}”对应的建议措施是什么？",
                kind="action_mode",
                row_index=idx,
                expected_terms=[action],
                reference_answer=action,
                expected_fields=["RecommendedAction"],
                difficulty="easy",
                style_tags=["mode_anchor", "natural_language"],
            )
        )

    add(
        _make_item(
            question=f"在项目/功能“{project}”里，失效模式“{mode}”这个问题，原因讲白一点是什么？",
            kind="cause_colloquial",
            row_index=idx,
            expected_terms=[cause],
            reference_answer=cause,
            difficulty="medium",
            style_tags=["colloquial"],
        )
    )
    add(
        _make_item(
            question=f"在项目/功能“{project}”里，失效模式“{mode}”最后会带来什么后果？",
            kind="effect_colloquial",
            row_index=idx,
            expected_terms=[effect],
            reference_answer=effect,
            difficulty="medium",
            style_tags=["colloquial"],
        )
    )
    if action:
        add(
            _make_item(
                question=f"在项目/功能“{project}”里，失效模式“{mode}”一般怎么处理？",
                kind="action_colloquial",
                row_index=idx,
                expected_terms=[action],
                reference_answer=action,
                difficulty="medium",
                style_tags=["colloquial"],
            )
        )
    add(
        _make_item(
            question=f"在项目/功能“{project}”里，失效模式“{mode}”的风险最后会体现成什么？",
            kind="risk_colloquial",
            row_index=idx,
            expected_terms=[effect],
            reference_answer=effect,
            difficulty="medium",
            style_tags=["colloquial"],
        )
    )

    add(
        _make_item(
            question=f"FMEA编号“{code}”对应的原因是否就是“{cause}”？",
            kind="cause_bool",
            row_index=idx,
            expected_fields=["是/否判断"],
            reference_answer="是",
            expected_bool=True,
            difficulty="easy",
            style_tags=["boolean"],
        )
    )
    add(
        _make_item(
            question=f"FMEA编号“{code}”对应的后果是否就是“{effect}”？",
            kind="risk_bool",
            row_index=idx,
            expected_fields=["是/否判断"],
            reference_answer="是",
            expected_bool=True,
            difficulty="easy",
            style_tags=["boolean"],
        )
    )
    add(
        _make_item(
            question=f"失效模式“{mode}”是不是出现在项目/功能“{project}”里？",
            kind="mode_project_bool",
            row_index=idx,
            expected_fields=["是/否判断"],
            reference_answer="是",
            expected_bool=True,
            difficulty="easy",
            style_tags=["boolean", "project_scope"],
        )
    )
    add(
        _make_item(
            question=f"失效模式“{mode}”对应的FMEA编号是什么？",
            kind="risk_mode_code",
            row_index=idx,
            expected_terms=[code],
            reference_answer=code,
            expected_fields=["FmeaID"],
            difficulty="easy",
            style_tags=["mode_anchor", "direct_lookup"],
        )
    )
    add(
        _make_item(
            question=f"在项目/功能“{project}”里，失效模式“{mode}”的后果是什么？",
            kind="risk_mode_project",
            row_index=idx,
            expected_terms=[effect],
            reference_answer=effect,
            difficulty="easy",
            style_tags=["project_scope", "natural_language"],
        )
    )

    return items


def _project_summary_questions(df: pd.DataFrame) -> dict[str, list[dict[str, Any]]]:
    items: dict[str, list[dict[str, Any]]] = {}
    projects = list(dict.fromkeys(_s(v) for v in df["ProcessStep"].tolist() if _s(v)))
    for project in projects:
        sub = df[df["ProcessStep"].map(_s) == project].copy()
        if sub.empty:
            continue
        rpn_values = pd.to_numeric(sub["RPN"], errors="coerce")
        avg_rpn = float(rpn_values.mean()) if rpn_values.notna().any() else None
        top_row = sub.loc[rpn_values.idxmax()] if rpn_values.notna().any() else sub.iloc[0]
        top_mode = _s(top_row.get("FailureMode"))
        top_rpn = _n(top_row.get("RPN"))
        top_effect = _s(top_row.get("FailureEffect"))

        project_items: list[dict[str, Any]] = []
        project_items.append(
            _make_item(
                question=f"项目/功能“{project}”的平均RPN是多少？",
                kind="project_avg_rpn",
                row_index=int(top_row.name) if top_row.name is not None else 0,
                expected_numbers=[avg_rpn] if avg_rpn is not None else [],
                reference_answer=f"平均RPN={avg_rpn:.2f}" if avg_rpn is not None else "",
                expected_fields=["RPN"],
                difficulty="medium",
                style_tags=["project_scope", "numeric_reasoning"],
            )
        )
        project_items.append(
            _make_item(
                question=f"项目/功能“{project}”里RPN最高的失效模式是什么？",
                kind="project_top_mode",
                row_index=int(top_row.name) if top_row.name is not None else 0,
                expected_terms=[top_mode],
                expected_numbers=[top_rpn] if top_rpn is not None else [],
                reference_answer=f"{top_mode}；RPN={top_rpn}",
                expected_fields=["FailureMode", "RPN"],
                difficulty="medium",
                style_tags=["project_scope", "numeric_reasoning"],
            )
        )
        if top_effect:
            project_items.append(
                _make_item(
                    question=f"项目/功能“{project}”里RPN最高的那条，它的后果是什么？",
                    kind="project_top_effect",
                    row_index=int(top_row.name) if top_row.name is not None else 0,
                    expected_terms=[top_effect],
                    reference_answer=top_effect,
                    expected_fields=["FailureEffect"],
                    difficulty="medium",
                    style_tags=["project_scope", "multi_hop"],
                )
            )
        items[project] = project_items
    return items


def build_questions(df: pd.DataFrame, total: int = 500) -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = []
    rows = df.reset_index(drop=False)
    project_items = _project_summary_questions(df)
    seen_projects: set[str] = set()
    for idx, row in rows.iterrows():
        project = _s(row.get("ProcessStep"))
        if project and project not in seen_projects:
            raw.extend(project_items.get(project, []))
            seen_projects.add(project)
        raw.extend(_balanced_row_questions(row, int(row["index"])))
    raw.extend(_global_questions(df))

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw, start=1):
        question = _s(item["question"])
        if not question or question in seen:
            continue
        seen.add(question)
        item = dict(item)
        item["idx"] = len(out) + 1
        out.append(item)
        if len(out) >= total:
            break

    if len(out) < total:
        # 兜底：对前面的题做轻微改写，填足数量。
        fallback_rows = rows.to_dict(orient="records")
        cursor = 0
        attempt = 0
        while len(out) < total and fallback_rows and attempt < total * 20:
            row = fallback_rows[cursor % len(fallback_rows)]
            code = _s(row.get("FmeaID"))
            mode = _s(row.get("FailureMode"))
            project = _s(row.get("ProcessStep"))
            effect = _s(row.get("FailureEffect"))
            cause = _s(row.get("FailureCause"))
            action = _s(row.get("RecommendedAction")) or _s(row.get("TempMeasure"))
            question = f"补题{attempt + 1}：再确认一下，{code}这条到底是{mode}，原因还是{cause}吗？"
            candidate = _make_item(
                question=question,
                kind="cause_multi",
                row_index=int(row.get("index", cursor)),
                expected_terms=[cause],
                reference_answer=cause,
                difficulty="medium",
                style_tags=["fallback", "multi_hop"],
            )
            q = _s(candidate["question"])
            if q not in seen:
                seen.add(q)
                candidate["idx"] = len(out) + 1
                out.append(candidate)
            cursor += 1
            attempt += 1

    return out[:total]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate 500 battery DFMEA evaluation questions.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--total", type=int, default=500)
    args = parser.parse_args()

    df = _df(Path(args.csv))
    questions = build_questions(df, total=max(1, int(args.total)))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in questions:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "csv": str(args.csv),
        "out": str(out_path),
        "total": len(questions),
        "categories": {
            "故障原因诊断类": sum(1 for q in questions if q["情景类别"] == "故障原因诊断类"),
            "故障措施推荐类": sum(1 for q in questions if q["情景类别"] == "故障措施推荐类"),
            "风险影响评估类": sum(1 for q in questions if q["情景类别"] == "风险影响评估类"),
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
