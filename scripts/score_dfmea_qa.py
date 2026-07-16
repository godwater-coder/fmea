# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

import pandas as pd


DEFAULT_CSV = Path("data/dfmea_final.csv")
DEFAULT_QUESTIONS = Path("answer/dfmea_100_questions.jsonl")
DEFAULT_PREDICTIONS = Path("answer/dfmea_100_answers.jsonl")
DEFAULT_COMPARE_CSV = Path("answer/dfmea_100_qa_compare.csv")
DEFAULT_OUT_CSV = Path("answer/dfmea_100_score_detail.csv")
DEFAULT_OUT_JSON = Path("answer/dfmea_100_score_summary.json")


PUNCT_RE = re.compile(r"[\s\u3000，。！？；：、,.!?;:\"'“”‘’（）()\[\]{}<>《》\-_/\\|]+")
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
QUOTE_RE = re.compile(r"[“\"‘']([^”\"’']+)[”\"’']")


@dataclass
class QuestionItem:
    idx: int
    question: str
    row_index: int
    kind: str


def norm_text(text: Any) -> str:
    s = "" if text is None else str(text)
    s = s.strip().lower()
    return PUNCT_RE.sub("", s)


def infer_boolean_expectation(question: str, gold_text: str) -> tuple[bool | None, str]:
    q = str(question or "")
    quoted = extract_quoted(q)
    if "是否" not in q or len(quoted) < 2:
        return None, ""
    target = quoted[-1]
    expected = norm_text(target) in norm_text(gold_text)
    return expected, target


def infer_boolean_answer(pred: str) -> bool | None:
    p = str(pred or "")
    if not p.strip():
        return None
    negative_patterns = ["不是", "不属于", "不包含", "不为", "否", "没有", "不存在", "不会", "不能"]
    positive_patterns = ["是", "属于", "包含", "为", "存在", "会", "正确", "可以"]
    for pat in negative_patterns:
        if pat in p:
            return False
    for pat in positive_patterns:
        if pat in p:
            return True
    return None


def extract_numbers(text: Any) -> list[float]:
    s = "" if text is None else str(text)
    out: list[float] = []
    for m in NUM_RE.findall(s):
        try:
            out.append(float(m))
        except Exception:
            pass
    return out


def extract_quoted(text: Any) -> list[str]:
    s = "" if text is None else str(text)
    return [x.strip() for x in QUOTE_RE.findall(s) if x and x.strip()]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def load_questions(path: Path) -> list[QuestionItem]:
    rows = load_jsonl(path)
    items: list[QuestionItem] = []
    for r in rows:
        items.append(
            QuestionItem(
                idx=int(r["idx"]),
                question=str(r["question"]),
                row_index=int(r.get("row_index", -1)),
                kind=str(r["kind"]),
            )
        )
    return items


def load_predictions(path: Path) -> dict[int, dict[str, Any]]:
    rows = load_jsonl(path)
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        out[int(r["idx"])] = r
    return out


def load_compare_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def make_ffill_df(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path).copy()
    if "设计项目" in df.columns:
        df["设计项目"] = df["设计项目"].ffill()
        df["设计项目"] = df["设计项目"].map(lambda x: "" if pd.isna(x) else str(x).strip())
    if "项目/功能" in df.columns:
        df["项目/功能"] = df["项目/功能"].ffill()
        df["项目/功能"] = df["项目/功能"].map(lambda x: "" if pd.isna(x) else str(x).strip())
    return df


def unique_nonempty(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        s = "" if v is None else str(v).strip()
        if not s or s.lower() == "nan":
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def contains_term(text: Any, term: Any) -> bool:
    t = norm_text(text)
    s = norm_text(term)
    return bool(t and s and s in t)


def parse_list_candidates(text: str) -> list[str]:
    raw = re.split(r"[，,；;。/、\n]+", str(text or ""))
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        s = str(item).strip()
        if not s:
            continue
        s = re.sub(r"^(包括|包含|分别是|分别为|是|有|对应的潜在失效模式包括[:：]?)", "", s).strip()
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def exact_number_match(gold: Any, pred: str, tol: float = 1e-6) -> tuple[bool, float]:
    nums = extract_numbers(pred)
    if gold is None or pd.isna(gold) or not nums:
        return False, float("inf")
    g = float(gold)
    delta = min(abs(x - g) for x in nums)
    return delta <= tol, delta


def known_terms_from_df(df: pd.DataFrame, columns: list[str]) -> list[str]:
    values: list[str] = []
    for col in columns:
        if col not in df.columns:
            continue
        values.extend(unique_nonempty(df[col].tolist()))
    return values


def exact_set_match(gold: list[str], pred: str, known_terms: list[str]) -> tuple[bool, list[str], list[str]]:
    pred_text = str(pred or "")
    missing = [g for g in gold if not contains_term(pred_text, g)]
    extras = [term for term in known_terms if term not in gold and contains_term(pred_text, term)]
    return not missing and not extras, missing, extras


def bool_or_text_exact_match(question: str, gold_terms: list[str], pred: str) -> tuple[bool, str]:
    gold_text = "；".join(gold_terms)
    expected, _ = infer_boolean_expectation(question, gold_text)
    if expected is not None:
        got = infer_boolean_answer(pred)
        return got is not None and got == expected, "boolean"
    if not gold_terms:
        return False, "missing_gold"
    return all(contains_term(pred, g) for g in gold_terms), "text"


def _base_columns(df: pd.DataFrame) -> dict[str, str]:
    return {
        "project": "设计项目" if "设计项目" in df.columns else "项目/功能",
        "mode": "潜在的失效模式" if "潜在的失效模式" in df.columns else "潜在失效模式",
        "effect": "潜在的失效后果" if "潜在的失效后果" in df.columns else "潜在失效后果",
        "cause": "潜在的失效原因/机理" if "潜在的失效原因/机理" in df.columns else "潜在失效原因/机理",
        "prev": "现行预防性设计控制" if "现行预防性设计控制" in df.columns else "现行预防控制",
        "det": "现行探测性设计控制" if "现行探测性设计控制" in df.columns else "现行探测控制",
        "s": "严重度" if "严重度" in df.columns else "严酷度(S)",
        "o": "频度数" if "频度数" in df.columns else "发生度(O)",
        "d": "探测度数" if "探测度数" in df.columns else "可探测度(D)",
        "rpn": "RPN" if "RPN" in df.columns else "风险优先数(RPN)",
        "code": "FMEA编号" if "FMEA编号" in df.columns else "",
        "product": "产品" if "产品" in df.columns else "",
        "action": "建议措施" if "建议措施" in df.columns else "",
    }


def _row_text(row: pd.Series, col: str) -> str:
    if not col:
        return ""
    value = row.get(col)
    if value is None or pd.isna(value):
        return ""
    s = str(value).strip()
    return "" if s.lower() == "nan" else s


def _project_rows(df: pd.DataFrame, project: str, cols: dict[str, str]) -> pd.DataFrame:
    project_col = cols["project"]
    if not project or not project_col:
        return df.iloc[0:0]
    return df[df[project_col].map(lambda x: str(x).strip()) == project]


def _terms_from_rows(rows: pd.DataFrame, col: str) -> list[str]:
    if not col or col not in rows.columns:
        return []
    return unique_nonempty(rows[col].tolist())


def _project_series_numeric(rows: pd.DataFrame, col: str) -> pd.Series:
    if not col or col not in rows.columns:
        return pd.Series([], dtype=float)
    return pd.to_numeric(rows[col], errors="coerce")


def _first_quoted(question: str) -> str:
    quoted = extract_quoted(question)
    return quoted[0] if quoted else ""


def _first_two_quoted(question: str) -> tuple[str, str]:
    quoted = extract_quoted(question)
    if len(quoted) >= 2:
        return quoted[0], quoted[1]
    if len(quoted) == 1:
        return quoted[0], ""
    return "", ""


def gold_for_item(df: pd.DataFrame, item: QuestionItem) -> dict[str, Any]:
    row = df.iloc[item.row_index] if 0 <= item.row_index < len(df) else df.iloc[0]
    def _pick(*keys: str) -> Any:
        for key in keys:
            if key in row.index:
                return row.get(key)
        return None

    cols = _base_columns(df)
    project_col = cols["project"]
    mode_col = cols["mode"]
    effect_col = cols["effect"]
    cause_col = cols["cause"]
    prev_col = cols["prev"]
    det_col = cols["det"]
    s_col = cols["s"]
    o_col = cols["o"]
    d_col = cols["d"]
    rpn_col = cols["rpn"]
    code_col = cols["code"]
    product_col = cols["product"]
    action_col = cols["action"]

    project = _row_text(row, project_col)
    mode = _row_text(row, mode_col)
    effect = _row_text(row, effect_col)
    cause = _row_text(row, cause_col)
    control_prev = _row_text(row, prev_col)
    control_det = _row_text(row, det_col)
    s = _pick(s_col)
    o = _pick(o_col)
    d = _pick(d_col)
    rpn = _pick(rpn_col)
    code = _row_text(row, code_col)
    product = _row_text(row, product_col)
    action = _row_text(row, action_col)

    project_rows = df[df[project_col] == project] if project else df.iloc[0:0]
    project_modes = unique_nonempty(project_rows[mode_col].tolist()) if len(project_rows) else []
    project_rpn = pd.to_numeric(project_rows[rpn_col], errors="coerce") if len(project_rows) else pd.Series([], dtype=float)

    if item.kind == "mode":
        return {"type": "set", "project": project, "gold": project_modes}
    if item.kind == "cause":
        return {"type": "text", "gold": [cause], "project": project}
    if item.kind == "effect":
        return {"type": "text", "gold": [effect], "project": project}
    if item.kind == "controls":
        return {"type": "set", "gold": unique_nonempty([control_prev, control_det])}
    if item.kind in {"rpn", "s", "o", "d"}:
        value_map = {"rpn": rpn, "s": s, "o": o, "d": d}
        return {"type": "number", "gold": value_map[item.kind]}
    if item.kind == "avg":
        mean_rpn = float(project_rpn.mean()) if len(project_rpn) else None
        return {"type": "number", "gold": round(mean_rpn, 2) if mean_rpn is not None else None}
    if item.kind == "max":
        if len(project_rpn):
            mx = float(project_rpn.max())
            modes = unique_nonempty(project_rows.loc[pd.to_numeric(project_rows[rpn_col], errors="coerce") == mx, mode_col].tolist())
        else:
            mx = None
            modes = []
        return {"type": "set", "gold": modes, "numeric": mx}
    if item.kind == "mode_project":
        return {"type": "text", "gold": [project]}
    if item.kind == "mode_code":
        return {"type": "text", "gold": [code]}
    if item.kind in {"mode_rpn", "mode_s", "mode_o", "mode_d"}:
        val_map = {"mode_rpn": rpn, "mode_s": s, "mode_o": o, "mode_d": d}
        return {"type": "number", "gold": val_map[item.kind]}
    if item.kind == "mode_cause":
        return {"type": "text", "gold": [cause]}
    if item.kind == "mode_effect":
        return {"type": "text", "gold": [effect]}
    if item.kind == "mode_controls":
        return {"type": "set", "gold": unique_nonempty([control_prev, control_det])}
    if item.kind == "mode_action":
        return {"type": "text", "gold": [action]}
    if item.kind in {
        "mode_boolean_cause",
        "mode_boolean_effect",
        "mode_boolean_project",
        "mode_boolean_product",
        "mode_boolean_rpn",
        "mode_boolean_s",
        "mode_boolean_o",
        "mode_boolean_d",
        "mode_boolean_prevent",
        "mode_boolean_detect",
        "mode_boolean_action",
        "mode_project_repeat",
        "mode_alt",
        "effect_alt",
        "cause_alt",
        "mode_has_prevent",
        "mode_has_detect",
        "project_has_mode",
        "project_has_effect",
        "project_has_cause",
        "project_max_mode_boolean",
        "project_min_mode_boolean",
        "project_max_rpn_boolean",
        "project_min_rpn_boolean",
        "global_has_mode",
        "global_has_low_mode",
        "global_has_effect",
        "global_has_cause",
        "global_has_project",
        "global_has_prevent",
        "global_has_detect",
        "global_has_action",
        "global_top_mode_rpn_boolean",
        "global_top_rpn_boolean",
        "global_low_rpn_boolean",
    }:
        base_map = {
            "mode_boolean_cause": [cause],
            "mode_boolean_effect": [effect],
            "mode_boolean_project": [project],
            "mode_boolean_product": [product],
            "mode_boolean_rpn": [str(rpn)],
            "mode_boolean_s": [str(s)],
            "mode_boolean_o": [str(o)],
            "mode_boolean_d": [str(d)],
            "mode_boolean_prevent": [control_prev],
            "mode_boolean_detect": [control_det],
            "mode_boolean_action": [action],
            "mode_project_repeat": [mode],
            "mode_alt": [mode, project],
            "effect_alt": [effect],
            "cause_alt": [cause],
            "mode_has_prevent": ["是" if bool(control_prev) else "否"],
            "mode_has_detect": ["是" if bool(control_det) else "否"],
        }
        if item.kind in base_map:
            return {"type": "text", "gold": base_map[item.kind]}
    if item.kind == "code_to_mode":
        return {"type": "text", "gold": [mode]}

    if item.kind.startswith("project_"):
        question_project = _first_quoted(item.question) or project
        rows = _project_rows(df, question_project, cols)
        modes = _terms_from_rows(rows, mode_col)
        effects = _terms_from_rows(rows, effect_col)
        causes = _terms_from_rows(rows, cause_col)
        prevents = _terms_from_rows(rows, prev_col)
        detects = _terms_from_rows(rows, det_col)
        actions = _terms_from_rows(rows, action_col)
        rpn_series = _project_series_numeric(rows, rpn_col)
        s_series = _project_series_numeric(rows, s_col)
        o_series = _project_series_numeric(rows, o_col)
        d_series = _project_series_numeric(rows, d_col)
        if item.kind == "project_modes":
            return {"type": "set", "gold": modes}
        if item.kind == "project_count":
            return {"type": "number", "gold": len(rows)}
        if item.kind == "project_avg_rpn":
            return {"type": "number", "gold": round(float(rpn_series.mean()), 2) if len(rpn_series) else None}
        if item.kind == "project_max_rpn_mode":
            mx = rpn_series.max() if len(rpn_series) else None
            gold = unique_nonempty(rows.loc[pd.to_numeric(rows[rpn_col], errors="coerce") == mx, mode_col].tolist()) if mx == mx else []
            return {"type": "set", "gold": gold}
        if item.kind == "project_min_rpn_mode":
            mn = rpn_series.min() if len(rpn_series) else None
            gold = unique_nonempty(rows.loc[pd.to_numeric(rows[rpn_col], errors="coerce") == mn, mode_col].tolist()) if mn == mn else []
            return {"type": "set", "gold": gold}
        if item.kind == "project_max_rpn_value":
            return {"type": "number", "gold": float(rpn_series.max()) if len(rpn_series) else None}
        if item.kind == "project_min_rpn_value":
            return {"type": "number", "gold": float(rpn_series.min()) if len(rpn_series) else None}
        if item.kind == "project_avg_s":
            return {"type": "number", "gold": round(float(s_series.mean()), 2) if len(s_series) else None}
        if item.kind == "project_avg_o":
            return {"type": "number", "gold": round(float(o_series.mean()), 2) if len(o_series) else None}
        if item.kind == "project_avg_d":
            return {"type": "number", "gold": round(float(d_series.mean()), 2) if len(d_series) else None}
        if item.kind == "project_effects":
            return {"type": "set", "gold": effects}
        if item.kind == "project_causes":
            return {"type": "set", "gold": causes}
        if item.kind == "project_prevents":
            return {"type": "set", "gold": prevents}
        if item.kind == "project_detects":
            return {"type": "set", "gold": detects}
        if item.kind == "project_actions":
            return {"type": "set", "gold": actions}
        if item.kind == "project_safety_count":
            return {"type": "number", "gold": int(sum(1 for x in rows[effect_col].tolist() if contains_term(x, "安全事故")))}
        if item.kind == "project_user_count":
            return {"type": "number", "gold": int(sum(1 for x in rows[effect_col].tolist() if contains_term(x, "影响用户使用")))}
        if item.kind == "project_threshold_high":
            gold = unique_nonempty(rows.loc[pd.to_numeric(rows[rpn_col], errors="coerce") >= 100, mode_col].tolist())
            return {"type": "set", "gold": gold}
        if item.kind == "project_threshold_low":
            gold = unique_nonempty(rows.loc[pd.to_numeric(rows[rpn_col], errors="coerce") <= 90, mode_col].tolist())
            return {"type": "set", "gold": gold}
        if item.kind in {"project_has_mode", "project_has_effect", "project_has_cause", "project_max_mode_boolean", "project_min_mode_boolean"}:
            target = extract_quoted(item.question)[1] if len(extract_quoted(item.question)) >= 2 else ""
            return {"type": "text", "gold": [target]}
        if item.kind == "project_max_rpn_boolean":
            return {"type": "text", "gold": [str(int(rpn_series.max())) if len(rpn_series) else ""]}
        if item.kind == "project_min_rpn_boolean":
            return {"type": "text", "gold": [str(int(rpn_series.min())) if len(rpn_series) else ""]}

    if item.kind.startswith("compare_"):
        left, right = _first_two_quoted(item.question)
        a_rows = _project_rows(df, left, cols)
        b_rows = _project_rows(df, right, cols)
        a_rpn = _project_series_numeric(a_rows, rpn_col)
        b_rpn = _project_series_numeric(b_rows, rpn_col)
        a_d = _project_series_numeric(a_rows, d_col)
        b_d = _project_series_numeric(b_rows, d_col)
        a_o = _project_series_numeric(a_rows, o_col)
        b_o = _project_series_numeric(b_rows, o_col)
        if item.kind == "compare_avg_rpn":
            return {"type": "text", "gold": [left if float(a_rpn.mean()) >= float(b_rpn.mean()) else right]}
        if item.kind == "compare_count":
            return {"type": "text", "gold": [left if len(a_rows) >= len(b_rows) else right]}
        if item.kind == "compare_max_rpn":
            return {"type": "text", "gold": [left if float(a_rpn.max()) >= float(b_rpn.max()) else right]}
        if item.kind == "compare_safety":
            a_n = sum(1 for x in a_rows[effect_col].tolist() if contains_term(x, "安全事故"))
            b_n = sum(1 for x in b_rows[effect_col].tolist() if contains_term(x, "安全事故"))
            return {"type": "text", "gold": [left if a_n >= b_n else right]}
        if item.kind == "compare_detect":
            return {"type": "text", "gold": [left if float(a_d.mean()) >= float(b_d.mean()) else right]}
        if item.kind == "compare_occurrence":
            return {"type": "text", "gold": [left if float(a_o.mean()) >= float(b_o.mean()) else right]}

    if item.kind.startswith("global_"):
        all_modes = _terms_from_rows(df, mode_col)
        all_effects = _terms_from_rows(df, effect_col)
        all_prevents = _terms_from_rows(df, prev_col)
        all_detects = _terms_from_rows(df, det_col)
        rpn_series = _project_series_numeric(df, rpn_col)
        s_series = _project_series_numeric(df, s_col)
        o_series = _project_series_numeric(df, o_col)
        d_series = _project_series_numeric(df, d_col)
        if item.kind == "global_count_modes":
            return {"type": "number", "gold": len(df)}
        if item.kind == "global_count_projects":
            return {"type": "number", "gold": len(unique_nonempty(df[project_col].tolist()))}
        if item.kind == "global_top_rpn_mode":
            mx = rpn_series.max()
            return {"type": "set", "gold": unique_nonempty(df.loc[pd.to_numeric(df[rpn_col], errors="coerce") == mx, mode_col].tolist())}
        if item.kind == "global_low_rpn_mode":
            mn = rpn_series.min()
            return {"type": "set", "gold": unique_nonempty(df.loc[pd.to_numeric(df[rpn_col], errors="coerce") == mn, mode_col].tolist())}
        if item.kind == "global_top_rpn_value":
            return {"type": "number", "gold": float(rpn_series.max())}
        if item.kind == "global_low_rpn_value":
            return {"type": "number", "gold": float(rpn_series.min())}
        if item.kind == "global_avg_rpn":
            return {"type": "number", "gold": round(float(rpn_series.mean()), 2)}
        if item.kind == "global_avg_s":
            return {"type": "number", "gold": round(float(s_series.mean()), 2)}
        if item.kind == "global_avg_o":
            return {"type": "number", "gold": round(float(o_series.mean()), 2)}
        if item.kind == "global_avg_d":
            return {"type": "number", "gold": round(float(d_series.mean()), 2)}
        if item.kind == "global_safety_modes":
            return {"type": "set", "gold": unique_nonempty(df.loc[df[effect_col].map(lambda x: contains_term(x, "安全事故")), mode_col].tolist())}
        if item.kind == "global_user_modes":
            return {"type": "set", "gold": unique_nonempty(df.loc[df[effect_col].map(lambda x: contains_term(x, "影响用户使用")), mode_col].tolist())}
        if item.kind == "global_work_modes":
            return {"type": "set", "gold": unique_nonempty(df.loc[df[effect_col].map(lambda x: contains_term(x, "影响电池工作")), mode_col].tolist())}
        if item.kind == "global_protect_modes":
            return {"type": "set", "gold": unique_nonempty(df.loc[df[prev_col].map(lambda x: contains_term(x, "提高防护等级")), mode_col].tolist())}
        if item.kind == "global_bit_modes":
            return {"type": "set", "gold": unique_nonempty(df.loc[df[det_col].map(lambda x: contains_term(x, "BIT机内测试")), mode_col].tolist())}
        if item.kind == "global_high_threshold":
            return {"type": "set", "gold": unique_nonempty(df.loc[pd.to_numeric(df[rpn_col], errors="coerce") >= 150, mode_col].tolist())}
        if item.kind == "global_low_threshold":
            return {"type": "set", "gold": unique_nonempty(df.loc[pd.to_numeric(df[rpn_col], errors="coerce") <= 90, mode_col].tolist())}
        if item.kind == "global_s10_modes":
            return {"type": "set", "gold": unique_nonempty(df.loc[pd.to_numeric(df[s_col], errors="coerce") == 10, mode_col].tolist())}
        if item.kind == "global_d6_modes":
            return {"type": "set", "gold": unique_nonempty(df.loc[pd.to_numeric(df[d_col], errors="coerce") == 6, mode_col].tolist())}
        if item.kind == "global_o2_modes":
            return {"type": "set", "gold": unique_nonempty(df.loc[pd.to_numeric(df[o_col], errors="coerce") == 2, mode_col].tolist())}
        if item.kind in {"global_has_mode", "global_has_low_mode", "global_has_effect", "global_has_cause", "global_has_project", "global_has_prevent", "global_has_detect", "global_has_action"}:
            target = extract_quoted(item.question)[0] if extract_quoted(item.question) else ""
            return {"type": "text", "gold": [target]}
        if item.kind == "global_top_mode_rpn_boolean":
            mx = rpn_series.max()
            top_modes = unique_nonempty(df.loc[pd.to_numeric(df[rpn_col], errors="coerce") == mx, mode_col].tolist())
            return {"type": "text", "gold": top_modes}
        if item.kind == "global_top_rpn_boolean":
            return {"type": "text", "gold": [str(int(rpn_series.max()))]}
        if item.kind == "global_low_rpn_boolean":
            return {"type": "text", "gold": [str(int(rpn_series.min()))]}
    return {"type": "text", "gold": []}


def score_item(df: pd.DataFrame, item: QuestionItem, pred_row: dict[str, Any]) -> dict[str, Any]:
    gold = gold_for_item(df, item)
    pred = str(pred_row.get("answer") or "")
    error = str(pred_row.get("error") or "")

    if error:
        return {
            "idx": item.idx,
            "kind": item.kind,
            "question": item.question,
            "answer": pred,
            "error": error,
            "score": 0,
            "correct": 0,
            "detail": "request_error",
        }

    if gold["type"] == "number":
        ok, delta = exact_number_match(gold["gold"], pred)
        return {
            "idx": item.idx,
            "kind": item.kind,
            "question": item.question,
            "answer": pred,
            "error": "",
            "score": int(ok),
            "correct": int(ok),
            "numeric_delta": round(float(delta), 6) if delta != float("inf") else "",
            "detail": "exact_number",
        }

    if gold["type"] == "set":
        if item.kind in {"mode", "max", "project_modes", "project_max_rpn_mode", "project_min_rpn_mode", "project_threshold_high", "project_threshold_low", "global_top_rpn_mode", "global_low_rpn_mode", "global_safety_modes", "global_user_modes", "global_work_modes", "global_protect_modes", "global_bit_modes", "global_high_threshold", "global_low_threshold", "global_s10_modes", "global_d6_modes", "global_o2_modes"}:
            mode_col = "潜在的失效模式" if "潜在的失效模式" in df.columns else "潜在失效模式"
            known_terms = known_terms_from_df(df, [mode_col])
        elif item.kind in {"controls", "mode_controls", "project_prevents", "project_detects"}:
            prev_col = "现行预防性设计控制" if "现行预防性设计控制" in df.columns else "现行预防控制"
            det_col = "现行探测性设计控制" if "现行探测性设计控制" in df.columns else "现行探测控制"
            known_terms = known_terms_from_df(df, [prev_col, det_col])
        elif item.kind in {"project_effects"}:
            effect_col = "潜在的失效后果" if "潜在的失效后果" in df.columns else "潜在失效后果"
            known_terms = known_terms_from_df(df, [effect_col])
        elif item.kind in {"project_causes"}:
            cause_col = "潜在的失效原因/机理" if "潜在的失效原因/机理" in df.columns else "潜在失效原因/机理"
            known_terms = known_terms_from_df(df, [cause_col])
        elif item.kind in {"project_actions"}:
            action_col = "建议措施" if "建议措施" in df.columns else ""
            known_terms = known_terms_from_df(df, [action_col] if action_col else [])
        else:
            known_terms = gold["gold"]
        ok, missing, extras = exact_set_match(gold["gold"], pred, known_terms)
        return {
            "idx": item.idx,
            "kind": item.kind,
            "question": item.question,
            "answer": pred,
            "error": "",
            "score": int(ok),
            "correct": int(ok),
            "missing_terms": "；".join(missing),
            "extra_terms": "；".join(extras),
            "detail": "exact_set",
        }

    gold_terms = gold.get("gold", [])
    ok, subtype = bool_or_text_exact_match(item.question, gold_terms, pred)
    return {
        "idx": item.idx,
        "kind": item.kind,
        "question": item.question,
        "answer": pred,
        "error": "",
        "score": int(ok),
        "correct": int(ok),
        "detail": f"exact_{subtype}",
    }


def score_compare_row(row: dict[str, Any]) -> dict[str, Any]:
    kind = str(row.get("kind") or "")
    question = str(row.get("question") or "")
    answer = str(row.get("answer") or "")
    gold_answer = str(row.get("gold_answer") or "")

    if kind in {"rpn", "s", "o", "d", "avg"}:
        gold_nums = extract_numbers(gold_answer)
        gold_num = gold_nums[-1] if gold_nums else None
        ok, delta = exact_number_match(gold_num, answer)
        return {
            "idx": int(row.get("idx") or 0),
            "kind": kind,
            "question": question,
            "answer": answer,
            "gold_answer": gold_answer,
            "score": int(ok),
            "correct": int(ok),
            "numeric_delta": round(float(delta), 6) if delta != float("inf") else "",
            "detail": "compare_exact_number",
        }

    if kind in {"mode", "controls", "max"}:
        gold_list = [x.strip() for x in re.split(r"[，,；;]", gold_answer) if x.strip()]
        ok = all(contains_term(answer, g) for g in gold_list)
        return {
            "idx": int(row.get("idx") or 0),
            "kind": kind,
            "question": question,
            "answer": answer,
            "gold_answer": gold_answer,
            "score": int(ok),
            "correct": int(ok),
            "detail": "compare_exact_set",
        }

    ok, subtype = bool_or_text_exact_match(question, [gold_answer], answer)
    return {
        "idx": int(row.get("idx") or 0),
        "kind": kind,
        "question": question,
        "answer": answer,
        "gold_answer": gold_answer,
        "score": int(ok),
        "correct": int(ok),
        "detail": f"compare_exact_{subtype}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Exact scoring for dfmea batch QA results.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="source dfmea csv")
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS), help="question jsonl")
    parser.add_argument("--predictions", default=str(DEFAULT_PREDICTIONS), help="prediction jsonl")
    parser.add_argument("--compare-csv", default="", help="score directly from compare csv answer/gold_answer")
    parser.add_argument("--out-csv", default=str(DEFAULT_OUT_CSV), help="detail csv output")
    parser.add_argument("--out-json", default=str(DEFAULT_OUT_JSON), help="summary json output")
    args = parser.parse_args()

    details: list[dict[str, Any]] = []
    source = "predictions_jsonl"
    if args.compare_csv:
        compare_rows = load_compare_csv(Path(args.compare_csv))
        details = [score_compare_row(row) for row in compare_rows]
        source = "compare_csv"
    else:
        df = make_ffill_df(Path(args.csv))
        questions = load_questions(Path(args.questions))
        preds = load_predictions(Path(args.predictions))
        for item in questions:
            pred = preds.get(item.idx, {"answer": "", "error": "missing_prediction"})
            details.append(score_item(df, item, pred))

    detail_path = Path(args.out_csv)
    detail_path.parent.mkdir(parents=True, exist_ok=True)
    with detail_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=sorted({k for row in details for k in row.keys()}))
        writer.writeheader()
        writer.writerows(details)

    scores = [float(d["score"]) for d in details]
    by_kind: dict[str, list[float]] = {}
    for d in details:
        by_kind.setdefault(d["kind"], []).append(float(d["score"]))

    summary = {
        "total": len(details),
        "exact_accuracy": round(mean(scores) if scores else 0.0, 4),
        "exact_correct": int(sum(1 for x in scores if x >= 1)),
        "kind_accuracy": {k: round(mean(v), 4) for k, v in sorted(by_kind.items())},
        "source": source,
        "detail_csv": str(detail_path),
    }

    out_json = Path(args.out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
