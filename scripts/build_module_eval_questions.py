# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import importlib.util
import json
from collections import Counter
from dataclasses import dataclass
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


MODULE_LABELS = {
    "M1": "M1_编号直答",
    "M2": "M2_规则推理",
    "M3": "M3_自然语言检索",
    "M4": "M4_证据裁决",
}

MODULE_NOTES = {
    "M1": "FMEA编号、字段明确、单条记录直答。",
    "M2": "平均、最高/最低、比较、S/O/D/RPN 等规则推理。",
    "M3": "无编号、自然语言直接查找、口语化或轻度噪声表达。",
    "M4": "是/否判断、证据是否存在、正负断言与裁决。",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def s(v: Any) -> str:
    if v is None:
        return ""
    if pd.isna(v):
        return ""
    return str(v).strip()


def n(v: Any) -> float | None:
    text = s(v)
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        return None


def pick_row(df: pd.DataFrame, idx: int) -> pd.Series:
    return df.iloc[idx % len(df)]


def usable(value: Any) -> bool:
    text = s(value)
    return bool(text and text.lower() not in {"nan", "none"} and text != "-")


def pick_from_pool(df: pd.DataFrame, pool: list[int], idx: int) -> pd.Series:
    if not pool:
        return pick_row(df, idx)
    return df.iloc[pool[idx % len(pool)]]


def first_nonempty(*values: Any) -> str:
    for value in values:
        text = s(value)
        if text and text.lower() != "nan" and text != "-":
            return text
    return ""


def infer_base_module(question: dict[str, Any]) -> str:
    preassigned = str(question.get("module_label") or question.get("primary_module_label") or "").strip()
    if preassigned in {"M1", "M2", "M3", "M4"}:
        return preassigned

    q = str(question.get("question") or "")
    kind = str(question.get("kind") or "")
    labels = question.get("labels") or []

    if kind.startswith("fmea_id_") or "fmea_id_anchor" in labels or "FMEA编号" in q:
        return "M1"

    # 这类题虽然不是显式“是/否”问法，但要求沿着后果、探测信息
    # 反向确认原因，属于证据链是否闭合的裁决题。
    if kind == "effect_detection_to_cause" or "判断" in q:
        return "M4"

    boolean_markers = ("是否", "是不是", "有没有", "能不能", "可不可以", "对不对", "是否为", "是否是")
    if any(x in q for x in boolean_markers) or "boolean" in kind:
        return "M4"

    reasoning_markers = (
        "平均", "最高", "最低", "多少", "几条", "几个", "比较", "对比", "分别", "哪个更",
        "RPN", "严酷度", "发生度", "可探测度", "S/O/D", "S、O、D",
    )
    if any(x in q for x in reasoning_markers):
        return "M2"

    return "M3"


def label_base_questions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        module = infer_base_module(row)
        new_row = dict(row)
        new_row["module_label"] = module
        new_row["module_label_name"] = MODULE_LABELS[module]
        new_row["module_label_note"] = MODULE_NOTES[module]
        new_row["primary_module_label"] = module
        out.append(new_row)
    return out


def generate_m1_questions(df: pd.DataFrame, limit: int, start_idx: int) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    templates = [
        ("cause", "FMEA编号“{code}”这条里，潜在失效原因/机理是什么？", ["潜在失效原因/机理"]),
        ("effect", "FMEA编号“{code}”这条里，潜在失效后果是什么？", ["潜在失效后果"]),
        ("rpn", "FMEA编号“{code}”这条的RPN是多少？", ["RPN"]),
        ("action", "FMEA编号“{code}”对应的建议措施是什么？", ["建议措施"]),
        ("sod", "FMEA编号“{code}”这条的S、O、D、RPN分别是多少？", ["严酷度(S)", "发生度(O)", "可探测度(D)", "RPN"]),
    ]
    field_pools = {
        "cause": [i for i, v in enumerate(df["潜在失效原因/机理"]) if usable(v)],
        "effect": [i for i, v in enumerate(df["潜在失效后果"]) if usable(v)],
        "rpn": [i for i, v in enumerate(df["风险优先数(RPN)"]) if n(v) is not None],
        "action": [i for i, v in enumerate(df["建议措施"]) if usable(v)],
        "sod": [
            i
            for i, row in df.iterrows()
            if all(n(row.get(c)) is not None for c in ("严酷度(S)", "发生度(O)", "可探测度(D)", "风险优先数(RPN)"))
        ],
    }
    for i in range(limit):
        kind = templates[i % len(templates)][0]
        row = pick_from_pool(df, field_pools[kind], i)
        code = first_nonempty(row.get("FMEA编号"))
        mode = first_nonempty(row.get("潜在失效模式"))
        project = first_nonempty(row.get("项目/功能"))
        cause = first_nonempty(row.get("潜在失效原因/机理"))
        effect = first_nonempty(row.get("潜在失效后果"))
        action = first_nonempty(row.get("建议措施"), row.get("临时采取的措施"))
        s_val = n(row.get("严酷度(S)"))
        o_val = n(row.get("发生度(O)"))
        d_val = n(row.get("可探测度(D)"))
        rpn = n(row.get("风险优先数(RPN)"))
        _, question_tmpl, expected_fields = templates[i % len(templates)]
        question = question_tmpl.format(code=code)
        expected_terms: list[str] = []
        expected_numbers: list[float] = []
        if kind == "cause":
            expected_terms = [cause]
        elif kind == "effect":
            expected_terms = [effect]
        elif kind == "rpn":
            expected_numbers = [rpn] if rpn is not None else []
        elif kind == "action":
            expected_terms = [action]
        elif kind == "sod":
            expected_numbers = [x for x in [s_val, o_val, d_val, rpn] if x is not None]
        questions.append(
            {
                "idx": start_idx + i,
                "scenario": "module_special_test",
                "情景类别": "模块专项测试",
                "kind": f"module_m1_{kind}",
                "tag": "module_m1_direct",
                "difficulty": "easy",
                "question": question,
                "expected_terms": expected_terms,
                "expected_numbers": expected_numbers,
                "expected_fields": expected_fields,
                "参考答案": cause if kind == "cause" else effect if kind == "effect" else action if kind == "action" else f"RPN={int(rpn) if rpn is not None and float(rpn).is_integer() else rpn}" if kind == "rpn" else "",
                "row_index": int(row.name) if row.name is not None else i,
                "labels": ["module_m1", "direct_code_lookup", "text_answer"],
                "primary_label": "module_m1",
                "labeling_method": "module_special_generation",
                "label_notes": "FMEA编号直答专项题。",
                "global_idx": start_idx + i,
                "module_label": "M1",
                "module_label_name": MODULE_LABELS["M1"],
                "module_label_note": MODULE_NOTES["M1"],
                "module_eval_target": "M1",
            }
        )
    return questions


def generate_m2_questions(df: pd.DataFrame, limit: int, start_idx: int) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    templates = [
        ("avg_rpn", "项目/功能“{project}”的平均RPN是多少？", ["RPN"]),
        ("max_mode", "项目/功能“{project}”中RPN最高的失效模式是什么？", ["潜在失效模式"]),
        ("min_mode", "项目/功能“{project}”中RPN最低的失效模式是什么？", ["潜在失效模式"]),
        ("mode_sod", "在“{project}”里，失效模式“{mode}”的S、O、D、RPN分别是多少？", ["严酷度(S)", "发生度(O)", "可探测度(D)", "RPN"]),
        ("avg_d", "项目/功能“{project}”的平均可探测度D是多少？", ["可探测度(D)"]),
    ]
    project_groups = {
        project: group
        for project, group in df.groupby(df["项目/功能"].map(s), sort=False)
        if project and len(group) >= 2
    }
    project_pool = list(project_groups)
    sod_pool = [
        i
        for i, row in df.iterrows()
        if all(n(row.get(c)) is not None for c in ("严酷度(S)", "发生度(O)", "可探测度(D)", "风险优先数(RPN)"))
    ]
    pair_counts = (
        df.assign(_project=df["项目/功能"].map(s), _mode=df["潜在失效模式"].map(s))
        .groupby(["_project", "_mode"])
        .size()
    )
    unique_sod_pool = [
        i
        for i, row in df.iterrows()
        if pair_counts.get((s(row.get("项目/功能")), s(row.get("潜在失效模式")),), 0) == 1
        and all(n(row.get(c)) is not None for c in ("严酷度(S)", "发生度(O)", "可探测度(D)", "风险优先数(RPN)"))
    ]
    for i in range(limit):
        kind = templates[i % len(templates)][0]
        if kind == "mode_sod" and unique_sod_pool:
            row = pick_from_pool(df, unique_sod_pool, i)
            project = first_nonempty(row.get("项目/功能"))
        elif kind in {"avg_rpn", "max_mode", "min_mode", "avg_d"} and project_pool:
            project = project_pool[i % len(project_pool)]
            row = project_groups[project].iloc[i % len(project_groups[project])]
        else:
            row = pick_from_pool(df, sod_pool, i)
            project = first_nonempty(row.get("项目/功能"))
        mode = first_nonempty(row.get("潜在失效模式"))
        rpn = n(row.get("风险优先数(RPN)"))
        s_val = n(row.get("严酷度(S)"))
        o_val = n(row.get("发生度(O)"))
        d_val = n(row.get("可探测度(D)"))
        _, question_tmpl, expected_fields = templates[i % len(templates)]
        question = question_tmpl.format(project=project, mode=mode)
        expected_terms: list[str] = []
        expected_numbers: list[float] = []
        if kind == "avg_rpn":
            sub = df[df["项目/功能"].map(s) == project]
            expected_numbers = [float(pd.to_numeric(sub["风险优先数(RPN)"], errors="coerce").mean())] if len(sub) else []
        elif kind == "max_mode":
            sub = df[df["项目/功能"].map(s) == project]
            if len(sub):
                sub_rpn = pd.to_numeric(sub["风险优先数(RPN)"], errors="coerce")
                max_rpn = sub_rpn.max()
                expected_terms = [first_nonempty(sub.loc[sub_rpn == max_rpn, "潜在失效模式"].iloc[0])]
        elif kind == "min_mode":
            sub = df[df["项目/功能"].map(s) == project]
            if len(sub):
                sub_rpn = pd.to_numeric(sub["风险优先数(RPN)"], errors="coerce")
                min_rpn = sub_rpn.min()
                expected_terms = [first_nonempty(sub.loc[sub_rpn == min_rpn, "潜在失效模式"].iloc[0])]
        elif kind == "mode_sod":
            expected_numbers = [x for x in [s_val, o_val, d_val, rpn] if x is not None]
        elif kind == "avg_d":
            sub = df[df["项目/功能"].map(s) == project]
            expected_numbers = [float(pd.to_numeric(sub["可探测度(D)"], errors="coerce").mean())] if len(sub) else []
        questions.append(
            {
                "idx": start_idx + i,
                "scenario": "module_special_test",
                "情景类别": "模块专项测试",
                "kind": f"module_m2_{kind}",
                "tag": "module_m2_reasoning",
                "difficulty": "medium",
                "question": question,
                "expected_terms": expected_terms,
                "expected_numbers": expected_numbers,
                "expected_fields": expected_fields,
                "参考答案": "",
                "row_index": int(row.name) if row.name is not None else i,
                "labels": ["module_m2", "numeric_reasoning", "multi_hop"],
                "primary_label": "module_m2",
                "labeling_method": "module_special_generation",
                "label_notes": "规则推理/比较/统计专项题。",
                "global_idx": start_idx + i,
                "module_label": "M2",
                "module_label_name": MODULE_LABELS["M2"],
                "module_label_note": MODULE_NOTES["M2"],
                "module_eval_target": "M2",
            }
        )
    return questions


def generate_m3_questions(df: pd.DataFrame, limit: int, start_idx: int) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    templates = [
        ("cause", "这个{project}里那个{mode}，到底咋回事，原因是啥？", ["潜在失效原因/机理"]),
        ("effect", "这个{project}里那个{mode}，最后会咋样，后果说下。", ["潜在失效后果"]),
        ("action", "这个{project}里那个{mode}，一般咋处理，给个法子。", ["建议措施"]),
        ("cause2", "我看这条有点糊，{project}那边的{mode}，为啥会出这个毛病？", ["潜在失效原因/机理"]),
        ("effect2", "这个{project}，{mode}这事会弄成啥后果，别太官方。", ["潜在失效后果"]),
    ]
    text_pools = {
        "cause": [
            i for i, row in df.iterrows()
            if usable(row.get("项目/功能"))
            and usable(row.get("潜在失效模式"))
            and usable(row.get("潜在失效原因/机理"))
        ],
        "effect": [
            i for i, row in df.iterrows()
            if usable(row.get("项目/功能"))
            and usable(row.get("潜在失效模式"))
            and usable(row.get("潜在失效后果"))
        ],
        "action": [
            i for i, row in df.iterrows()
            if usable(row.get("项目/功能"))
            and usable(row.get("潜在失效模式"))
            and usable(row.get("建议措施"))
        ],
    }
    for i in range(limit):
        kind = templates[i % len(templates)][0]
        pool_kind = "cause" if "cause" in kind else "effect" if "effect" in kind else "action"
        row = pick_from_pool(df, text_pools[pool_kind], i)
        project = first_nonempty(row.get("项目/功能"))
        mode = first_nonempty(row.get("潜在失效模式"))
        cause = first_nonempty(row.get("潜在失效原因/机理"))
        effect = first_nonempty(row.get("潜在失效后果"))
        action = first_nonempty(row.get("建议措施"), row.get("临时采取的措施"))
        kind, question_tmpl, expected_fields = templates[i % len(templates)]
        # 不给自然语言专项题加引号，也不暴露 FMEA 编号，避免它们
        # 被“编号/引号实体”规则误判成 M1。
        question = question_tmpl.format(project=project, mode=mode)
        expected_terms = [cause] if "cause" in kind else [effect] if "effect" in kind else [action]
        questions.append(
            {
                "idx": start_idx + i,
                "scenario": "module_special_test",
                "情景类别": "模块专项测试",
                "kind": f"module_m3_{kind}",
                "tag": "module_m3_colloquial",
                "difficulty": "medium",
                "question": question,
                "expected_terms": expected_terms,
                "expected_numbers": [],
                "expected_fields": expected_fields,
                "参考答案": expected_terms[0] if expected_terms else "",
                "row_index": int(row.name) if row.name is not None else i,
                "labels": ["module_m3", "colloquial", "retrieval", "text_answer"],
                "primary_label": "module_m3",
                "labeling_method": "module_special_generation",
                "label_notes": "口语化/模糊检索专项题。",
                "global_idx": start_idx + i,
                "module_label": "M3",
                "module_label_name": MODULE_LABELS["M3"],
                "module_label_note": MODULE_NOTES["M3"],
                "module_eval_target": "M3",
            }
        )
    return questions


def generate_m4_questions(df: pd.DataFrame, limit: int, start_idx: int) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    nonempty_action = [i for i, v in enumerate(df["建议措施"]) if usable(v)]
    projects = list(dict.fromkeys(df["项目/功能"].map(s)))
    modes = list(dict.fromkeys(df["潜在失效模式"].map(s)))
    for i in range(limit):
        row = pick_row(df, i)
        other = pick_row(df, i + 17)
        code = first_nonempty(row.get("FMEA编号"))
        project = first_nonempty(row.get("项目/功能"))
        mode = first_nonempty(row.get("潜在失效模式"))
        effect = first_nonempty(row.get("潜在失效后果"))
        cause = first_nonempty(row.get("潜在失效原因/机理"))
        action = first_nonempty(row.get("建议措施"), row.get("临时采取的措施"))
        prevent = first_nonempty(row.get("现行预防控制"))
        detect = first_nonempty(row.get("现行探测控制"))
        other_project = first_nonempty(other.get("项目/功能"))
        other_mode = first_nonempty(other.get("潜在失效模式"))
        other_effect = first_nonempty(other.get("潜在失效后果"))

        template_id = i % 6
        if template_id == 0:
            row = pick_from_pool(df, nonempty_action, i)
            code = first_nonempty(row.get("FMEA编号"))
            action = first_nonempty(row.get("建议措施"), row.get("临时采取的措施"))
            question = f'FMEA编号“{code}”是不是有写建议措施？'
            expected_bool = bool(action and action != "-")
        elif template_id == 1:
            question = f'项目/功能“{project}”里有没有“{mode}”这个问题？'
            expected_bool = True
        elif template_id == 2:
            question = f'失效模式“{mode}”的后果是不是“{effect}”？'
            expected_bool = True
        elif template_id == 3:
            other_project = other_project if other_project != project else projects[(i + 1) % len(projects)]
            question = f'FMEA编号“{code}”是不是属于项目/功能“{other_project}”？'
            expected_bool = bool(project == other_project)
        elif template_id == 4:
            # 构造一个尽量不成立的“项目-失效模式”组合。
            other_mode = modes[(i + 1) % len(modes)]
            if other_mode == mode:
                other_mode = modes[(i + 2) % len(modes)]
            cand = df[(df["项目/功能"].map(s) == project) & (df["潜在失效模式"].map(s) == other_mode)]
            if cand.empty:
                question = f'项目/功能“{project}”里有没有“{other_mode}”这个问题？'
                expected_bool = False
            else:
                # 兜底：如果刚好命中，就换成一个明确不在该项目下的模式。
                other_project_modes = [m for m in modes if df[(df["项目/功能"].map(s) == project) & (df["潜在失效模式"].map(s) == m)].empty]
                if other_project_modes:
                    other_mode = other_project_modes[0]
                    question = f'项目/功能“{project}”里有没有“{other_mode}”这个问题？'
                    expected_bool = False
                else:
                    question = f'项目/功能“{project}”里有没有“{other_mode}”这个问题？'
                    expected_bool = False
        else:
            question = f'这条记录的现行预防控制是不是空的？'
            expected_bool = not bool(prevent)

        questions.append(
            {
                "idx": start_idx + i,
                "scenario": "module_special_test",
                "情景类别": "模块专项测试",
                "kind": f"module_m4_bool_{template_id}",
                "tag": "module_m4_adjudication",
                "difficulty": "hard",
                "question": question,
                "expected_bool": expected_bool,
                "expected_terms": [],
                "expected_numbers": [],
                "expected_fields": ["是/否判断"],
                "参考答案": "是" if expected_bool else "否",
                "row_index": int(row.name) if row.name is not None else i,
                "labels": ["module_m4", "boolean", "evidence_judgement", "multi_hop"],
                "primary_label": "module_m4",
                "labeling_method": "module_special_generation",
                "label_notes": "证据裁决/是非判断专项题。",
                "global_idx": start_idx + i,
                "module_label": "M4",
                "module_label_name": MODULE_LABELS["M4"],
                "module_label_note": MODULE_NOTES["M4"],
                "module_eval_target": "M4",
            }
        )
    return questions


def main() -> int:
    parser = argparse.ArgumentParser(description="Build module-tagged evaluation questions.")
    parser.add_argument("--base-jsonl", default="DATA/zenodo_floating_wind_fmea/scenario_qa_no_id/all_scenario_no_id_1500_questions.jsonl")
    parser.add_argument("--csv", default="DATA/zenodo_floating_wind_fmea/zenodo_fmea_project_import.csv")
    parser.add_argument("--out", default="DATA/zenodo_floating_wind_fmea/module_eval/all_module_eval_1900_questions.jsonl")
    parser.add_argument("--extra-per-module", type=int, default=100)
    parser.add_argument("--summary", default="DATA/zenodo_floating_wind_fmea/module_eval/module_eval_summary.json")
    parser.add_argument(
        "--labeled-base-out",
        default="DATA/zenodo_floating_wind_fmea/module_eval/labeled_base_1500_questions.jsonl",
    )
    parser.add_argument(
        "--special-dir",
        default="DATA/zenodo_floating_wind_fmea/module_eval/special",
    )
    parser.add_argument(
        "--special-all-out",
        default="DATA/zenodo_floating_wind_fmea/module_eval/special_all_400_questions.jsonl",
    )
    args = parser.parse_args()

    base_rows = load_jsonl(Path(args.base_jsonl))
    labeled_base = label_base_questions(base_rows)
    df = rename_standard_headers(pd.read_csv(Path(args.csv)))
    if "ProcessStep" in df.columns:
        df["ProcessStep"] = df["ProcessStep"].ffill()
    alias_map = {
        "设计项目": "ProcessStep",
        "项目/功能": "ProcessStep",
        "过程步骤": "ProcessStep",
        "工序": "ProcessStep",
        "潜在的失效模式": "FailureMode",
        "潜在失效模式": "FailureMode",
        "潜在的失效后果": "FailureEffect",
        "潜在失效后果": "FailureEffect",
        "潜在的失效原因/机理": "FailureCause",
        "潜在失效原因/机理": "FailureCause",
        "潜在失效原因": "FailureCause",
        "严重度": "S",
        "严酷度(S)": "S",
        "频度数": "O",
        "发生度": "O",
        "发生度(O)": "O",
        "探测度数": "D",
        "探测度": "D",
        "可探测度(D)": "D",
        "RPN": "RPN",
        "风险优先数(RPN)": "RPN",
        "现行预防性设计控制": "PreventControl",
        "现行预防控制": "PreventControl",
        "现行探测性设计控制": "DetectionMeasure",
        "现行探测性控制": "DetectionMeasure",
        "现行探测控制": "DetectionMeasure",
        "建议措施": "RecommendedAction",
        "临时采取的措施": "RecommendedAction",
        "FMEA编号": "FmeaID",
        "产品": "Product",
        "分析层级": "AnalysisLevel",
    }
    for alias, source in alias_map.items():
        if source in df.columns and alias not in df.columns:
            df[alias] = df[source]
    extra_start = len(labeled_base) + 1
    extras: list[dict[str, Any]] = []
    extras.extend(generate_m1_questions(df, args.extra_per_module, extra_start))
    extras.extend(generate_m2_questions(df, args.extra_per_module, extra_start + len(extras)))
    extras.extend(generate_m3_questions(df, args.extra_per_module, extra_start + len(extras)))
    extras.extend(generate_m4_questions(df, args.extra_per_module, extra_start + len(extras)))

    combined = labeled_base + extras
    for i, row in enumerate(combined, start=1):
        row["idx"] = i
        row["global_idx"] = i

    out_path = Path(args.out)
    write_jsonl(out_path, combined)
    write_jsonl(Path(args.labeled_base_out), labeled_base)
    special_dir = Path(args.special_dir)
    special_rows: list[dict[str, Any]] = []
    for module in ("M1", "M2", "M3", "M4"):
        module_rows = [row for row in extras if row.get("module_eval_target") == module]
        special_rows.extend(module_rows)
        write_jsonl(
            special_dir / f"module_{module.lower()}_{args.extra_per_module}_questions.jsonl",
            module_rows,
        )
    write_jsonl(Path(args.special_all_out), special_rows)

    module_counts = Counter(row.get("module_label_name") for row in combined)
    summary = {
        "base_file": args.base_jsonl,
        "csv": args.csv,
        "out": args.out,
        "total": len(combined),
        "base_total": len(labeled_base),
        "extra_per_module": args.extra_per_module,
        "module_counts": dict(module_counts),
        "base_module_counts": dict(Counter(row.get("module_label_name") for row in labeled_base)),
        "extra_module_counts": dict(Counter(row.get("module_label_name") for row in extras)),
    }
    write_json(Path(args.summary), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
