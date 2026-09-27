# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


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
DEFAULT_OUT = Path("DATA/磷酸铁锂电池Dfmea分析/module_eval/lfp_module_special_200_questions.jsonl")
DEFAULT_DIR = Path("DATA/磷酸铁锂电池Dfmea分析/module_eval/special")


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


def _build_item(
    *,
    idx: int,
    module: str,
    module_name: str,
    module_note: str,
    question: str,
    kind: str,
    row_index: int,
    labels: list[str],
    difficulty: str,
    expected_terms: list[str] | None = None,
    expected_numbers: list[float] | None = None,
    expected_fields: list[str] | None = None,
    expected_bool: bool | None = None,
    expected_intent: str = "",
    expected_entities: list[dict[str, str]] | None = None,
    expected_metric: str = "",
    expected_constraints: list[dict[str, str]] | None = None,
    expected_route: str = "",
    should_reject: bool = False,
    reference_answer: str = "",
) -> dict[str, Any]:
    item = {
        "idx": idx,
        "scenario": "battery_dfmea_module_special",
        "情景类别": "模块专项测试",
        "kind": kind,
        "题型": kind,
        "标签": labels[0] if labels else "",
        "difficulty": difficulty,
        "question": question,
        "expected_terms": expected_terms or [],
        "expected_numbers": expected_numbers or [],
        "expected_fields": expected_fields or [],
        "参考答案": reference_answer,
        "row_index": row_index,
        "labels": labels,
        "primary_label": labels[0] if labels else "",
        "labeling_method": "battery_dfmea_module_special",
        "label_notes": "磷酸铁锂电池 DFMEA 模块专项题。",
        "module_label": module,
        "module_label_name": module_name,
        "module_label_note": module_note,
        "module_eval_target": module,
        "source_domain": "磷酸铁锂电池DFMEA",
        "expected_intent": expected_intent,
        "expected_entities": expected_entities or [],
        "expected_metric": expected_metric,
        "expected_constraints": expected_constraints or [],
        "expected_route": expected_route or {"M1": "csv_basic", "M2": "deterministic_rule", "M3": "semantic_rag"}.get(module, ""),
        "should_reject": bool(should_reject),
    }
    if expected_bool is not None:
        item["expected_bool"] = bool(expected_bool)
    return item


def _m1_questions(df: pd.DataFrame, limit: int, start_idx: int) -> list[dict[str, Any]]:
    rows = df.reset_index(drop=False)
    templates = [
        ("cause", "编号{code}对应的原因到底是什么？", ["潜在失效原因/机理"]),
        ("effect", "编号{code}对应的后果是什么？", ["潜在失效后果"]),
        ("action", "编号{code}建议咋改？", ["建议措施"]),
        ("rpn", "编号{code}的RPN是多少？", ["RPN"]),
        ("sod", "编号{code}的S、O、D、RPN分别是多少？", ["S", "O", "D", "RPN"]),
    ]
    out: list[dict[str, Any]] = []
    for i in range(limit):
        row = rows.iloc[i % len(rows)]
        code = _s(row.get("FmeaID"))
        mode = _s(row.get("FailureMode"))
        cause = _s(row.get("FailureCause"))
        effect = _s(row.get("FailureEffect"))
        action = _s(row.get("RecommendedAction")) or _s(row.get("TempMeasure"))
        s_val = _n(row.get("S"))
        o_val = _n(row.get("O"))
        d_val = _n(row.get("D"))
        rpn = _n(row.get("RPN"))
        kind, tmpl, fields = templates[i % len(templates)]
        question = tmpl.format(code=code, mode=mode)
        expected_terms: list[str] = []
        expected_numbers: list[float] = []
        reference = ""
        if kind == "cause":
            expected_terms = [cause]
            reference = cause
        elif kind == "effect":
            expected_terms = [effect]
            reference = effect
        elif kind == "action":
            expected_terms = [action]
            reference = action
        elif kind == "rpn":
            expected_numbers = [rpn] if rpn is not None else []
            reference = f"RPN={rpn}"
        else:
            expected_numbers = [x for x in (s_val, o_val, d_val, rpn) if x is not None]
            reference = f"S={s_val}；O={o_val}；D={d_val}；RPN={rpn}"
        out.append(
            _build_item(
                idx=start_idx + i,
                module="M1",
                module_name="M1_编号直答",
                module_note="编号直答",
                question=question,
                kind=f"module_m1_{kind}",
                row_index=int(row["index"]),
                labels=["module_m1", "direct_code_lookup", "battery_module_special"],
                difficulty="easy",
                expected_terms=expected_terms,
                expected_numbers=expected_numbers,
                expected_fields=fields,
                reference_answer=reference,
            )
        )
    return out


def _m2_questions(df: pd.DataFrame, limit: int, start_idx: int) -> list[dict[str, Any]]:
    rows = df.reset_index(drop=False)
    project_groups = {k: g.reset_index(drop=False).copy() for k, g in df.groupby("ProcessStep", sort=False)}
    projects = list(project_groups)
    templates = [
        ("avg_rpn", "项目/功能“{project}”的平均RPN是多少？", ["RPN"]),
        ("max_mode", "项目/功能“{project}”里RPN最高的是哪条？", ["FailureMode"]),
        ("min_mode", "项目/功能“{project}”里RPN最低的是哪条？", ["FailureMode"]),
        ("avg_s", "项目/功能“{project}”的平均S是多少？", ["S"]),
        ("avg_d", "项目/功能“{project}”的平均D是多少？", ["D"]),
    ]
    out: list[dict[str, Any]] = []
    for i in range(limit):
        project = projects[i % len(projects)]
        sub = project_groups[project]
        row = sub.iloc[i % len(sub)]
        rpn_series = pd.to_numeric(sub["RPN"], errors="coerce")
        s_series = pd.to_numeric(sub["S"], errors="coerce")
        d_series = pd.to_numeric(sub["D"], errors="coerce")
        kind, tmpl, fields = templates[i % len(templates)]
        question = tmpl.format(project=project)
        expected_terms: list[str] = []
        expected_numbers: list[float] = []
        reference = ""
        if kind == "avg_rpn":
            val = float(rpn_series.mean()) if rpn_series.notna().any() else None
            expected_numbers = [val] if val is not None else []
            reference = f"平均RPN={val:.2f}" if val is not None else ""
        elif kind == "max_mode":
            idx_max = rpn_series.idxmax()
            mode = _s(sub.loc[idx_max, "FailureMode"])
            expected_terms = [mode]
            reference = mode
        elif kind == "min_mode":
            idx_min = rpn_series.idxmin()
            mode = _s(sub.loc[idx_min, "FailureMode"])
            expected_terms = [mode]
            reference = mode
        elif kind == "avg_s":
            val = float(s_series.mean()) if s_series.notna().any() else None
            expected_numbers = [val] if val is not None else []
            reference = f"平均S={val:.2f}" if val is not None else ""
        else:
            val = float(d_series.mean()) if d_series.notna().any() else None
            expected_numbers = [val] if val is not None else []
            reference = f"平均D={val:.2f}" if val is not None else ""
        out.append(
            _build_item(
                idx=start_idx + i,
                module="M2",
                module_name="M2_规则推理",
                module_note="规则推理",
                question=question,
                kind=f"module_m2_{kind}",
                row_index=int(row["index"]),
                labels=["module_m2", "numeric_reasoning", "battery_module_special"],
                difficulty="medium",
                expected_terms=expected_terms,
                expected_numbers=expected_numbers,
                expected_fields=fields,
                reference_answer=reference,
            )
        )
    return out


def _m3_questions(df: pd.DataFrame, limit: int, start_idx: int) -> list[dict[str, Any]]:
    rows = df.reset_index(drop=False)
    templates = [
        ("cause", "这条{mode}咋冒出来的，原因说白一点。", ["潜在失效原因/机理"]),
        ("effect", "这个{mode}最后会怎么样，别说太官方。", ["潜在失效后果"]),
        ("action", "这个{mode}要是碰上了，现场一般怎么收拾？", ["建议措施"]),
        ("cause2", "{project}那边这个事儿，听着像是咋引起的？", ["潜在失效原因/机理"]),
        ("effect2", "{project}里这个{mode}，会把事情搞成什么样？", ["潜在失效后果"]),
    ]
    pools = {
        "cause": [i for i, row in rows.iterrows() if _s(row.get("FailureCause")) and _s(row.get("FailureMode"))],
        "effect": [i for i, row in rows.iterrows() if _s(row.get("FailureEffect")) and _s(row.get("FailureMode"))],
        "action": [i for i, row in rows.iterrows() if _s(row.get("RecommendedAction")) and _s(row.get("FailureMode"))],
    }
    out: list[dict[str, Any]] = []
    for i in range(limit):
        kind, tmpl, fields = templates[i % len(templates)]
        pool_kind = "cause" if "cause" in kind else "effect" if "effect" in kind else "action"
        row = rows.iloc[pools[pool_kind][i % len(pools[pool_kind])]]
        project = _s(row.get("ProcessStep"))
        mode = _s(row.get("FailureMode"))
        cause = _s(row.get("FailureCause"))
        effect = _s(row.get("FailureEffect"))
        action = _s(row.get("RecommendedAction")) or _s(row.get("TempMeasure"))
        question = tmpl.format(project=project, mode=mode)
        expected_terms = [cause] if "cause" in kind else [effect] if "effect" in kind else [action]
        reference = expected_terms[0] if expected_terms else ""
        out.append(
            _build_item(
                idx=start_idx + i,
                module="M3",
                module_name="M3_查询理解与语义检索增强",
                module_note="口语化/模糊检索",
                question=question,
                kind=f"module_m3_{kind}",
                row_index=int(row["index"]),
                labels=["module_m3", "colloquial", "battery_module_special"],
                difficulty="medium",
                expected_terms=expected_terms,
                expected_fields=fields,
                reference_answer=reference,
            )
        )
    return out


def _m4_questions(df: pd.DataFrame, limit: int, start_idx: int) -> list[dict[str, Any]]:
    rows = df.reset_index(drop=False)
    projects = list(dict.fromkeys(rows["ProcessStep"].map(_s).tolist()))
    modes = list(dict.fromkeys(rows["FailureMode"].map(_s).tolist()))
    out: list[dict[str, Any]] = []
    for i in range(limit):
        row = rows.iloc[i % len(rows)]
        project = _s(row.get("ProcessStep"))
        mode = _s(row.get("FailureMode"))
        effect = _s(row.get("FailureEffect"))
        cause = _s(row.get("FailureCause"))
        prevent = _s(row.get("PreventControl"))
        detect = _s(row.get("DetectionMeasure"))
        action = _s(row.get("RecommendedAction")) or _s(row.get("TempMeasure"))
        template_id = i % 5
        should_reject = False
        if template_id == 0:
            question = f"编号{_s(row.get('FmeaID'))}是不是有写建议措施？"
            expected_bool = bool(action)
        elif template_id == 1:
            question = f"项目/功能“{project}”里有没有“{mode}”这个问题？"
            expected_bool = True
        elif template_id == 2:
            question = f"这个{mode}的后果是不是“{effect}”？"
            expected_bool = True
        elif template_id == 3:
            other = projects[(i + 1) % len(projects)]
            question = f"项目/功能“{project}”里会不会出现“{mode}”这个问题在“{other}”里？"
            expected_bool = project == other
        else:
            question = f"请给出编号LFP-NOT-FOUND-{i + 1}的S、O、D和RPN。"
            expected_bool = None
            should_reject = True
        out.append(
            _build_item(
                idx=start_idx + i,
                module="M4",
                module_name="M4_证据裁决",
                module_note="证据裁决",
                question=question,
                kind=f"module_m4_bool_{template_id}",
                row_index=int(row["index"]),
                labels=["module_m4", "boolean", "battery_module_special"],
                difficulty="hard",
                expected_fields=["是/否判断"],
                expected_bool=bool(expected_bool) if expected_bool is not None else None,
                should_reject=should_reject,
                expected_route="reject" if should_reject else "",
                reference_answer="证据不足，应拒答" if should_reject else ("是" if expected_bool else "否"),
            )
        )
    return out


def build_questions(df: pd.DataFrame, per_module: int = 50) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    items.extend(_m1_questions(df, per_module, 1))
    items.extend(_m2_questions(df, per_module, 1 + len(items)))
    items.extend(_m3_questions(df, per_module, 1 + len(items)))
    items.extend(_m4_questions(df, per_module, 1 + len(items)))
    for idx, item in enumerate(items, start=1):
        item["idx"] = idx
        item["global_idx"] = idx
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate 200 battery module-special questions.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--special-dir", default=str(DEFAULT_DIR))
    parser.add_argument("--per-module", type=int, default=50)
    args = parser.parse_args()

    df = _df(Path(args.csv))
    questions = build_questions(df, per_module=max(1, int(args.per_module)))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in questions:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    special_dir = Path(args.special_dir)
    special_dir.mkdir(parents=True, exist_ok=True)
    for module in ("M1", "M2", "M3", "M4"):
        rows = [r for r in questions if r.get("module_eval_target") == module]
        with (special_dir / f"module_{module.lower()}_{args.per_module}_questions.jsonl").open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "csv": str(args.csv),
        "out": str(out_path),
        "total": len(questions),
        "per_module": int(args.per_module),
        "module_counts": {
            module: sum(1 for r in questions if r.get("module_eval_target") == module)
            for module in ("M1", "M2", "M3", "M4")
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
