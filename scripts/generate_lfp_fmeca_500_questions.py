# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


DEFAULT_CSV = Path("data/磷酸铁锂电池FMECA分析表20250416105822.csv")
DEFAULT_OUT = Path("answer/lfp_fmeca_500_questions.jsonl")


def _s(v: object) -> str:
    if v is None:
        return ""
    if pd.isna(v):
        return ""
    return str(v).strip()


def _uniq_keep_order(items: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[str] = set()
    out: list[dict[str, object]] = []
    for item in items:
        q = str(item["question"]).strip()
        if not q or q in seen:
            continue
        seen.add(q)
        out.append(
            {
                "kind": str(item["kind"]).strip(),
                "question": q,
                "row_index": int(item.get("row_index", -1)),
            }
        )
    return out


def _row_questions(row: pd.Series, row_index: int) -> list[dict[str, object]]:
    mode = _s(row.get("潜在失效模式"))
    effect = _s(row.get("潜在失效后果"))
    cause = _s(row.get("潜在失效原因/机理"))
    project = _s(row.get("项目/功能"))
    fid = _s(row.get("FMEA编号"))
    rpn = _s(row.get("风险优先数(RPN)"))
    s_val = _s(row.get("严酷度(S)"))
    o_val = _s(row.get("发生度(O)"))
    d_val = _s(row.get("可探测度(D)"))
    prevent = _s(row.get("现行预防控制"))
    detect = _s(row.get("现行探测控制"))
    action = _s(row.get("建议措施"))
    product = _s(row.get("产品"))

    items: list[dict[str, str]] = []

    if mode:
        items.extend(
            [
                {"kind": "mode_project", "question": f"失效模式“{mode}”属于哪个项目/功能？", "row_index": row_index},
                {"kind": "mode_code", "question": f"失效模式“{mode}”对应的FMEA编号是什么？", "row_index": row_index},
                {"kind": "mode_rpn", "question": f"失效模式“{mode}”的RPN是多少？", "row_index": row_index},
                {"kind": "mode_s", "question": f"失效模式“{mode}”的严酷度S是多少？", "row_index": row_index},
                {"kind": "mode_o", "question": f"失效模式“{mode}”的发生度O是多少？", "row_index": row_index},
                {"kind": "mode_d", "question": f"失效模式“{mode}”的可探测度D是多少？", "row_index": row_index},
                {"kind": "mode_cause", "question": f"失效模式“{mode}”的潜在失效原因/机理是什么？", "row_index": row_index},
                {"kind": "mode_effect", "question": f"失效模式“{mode}”的潜在失效后果是什么？", "row_index": row_index},
                {"kind": "mode_controls", "question": f"针对失效模式“{mode}”，现行预防控制和现行探测控制分别是什么？", "row_index": row_index},
                {"kind": "mode_action", "question": f"针对失效模式“{mode}”，建议措施是什么？", "row_index": row_index},
                {"kind": "mode_boolean_cause", "question": f"失效模式“{mode}”的原因是否包含“{cause}”？", "row_index": row_index} if cause else {},
                {"kind": "mode_boolean_effect", "question": f"失效模式“{mode}”的后果是否为“{effect}”？", "row_index": row_index} if effect else {},
                {"kind": "mode_boolean_project", "question": f"失效模式“{mode}”是否属于“{project}”？", "row_index": row_index} if project else {},
                {"kind": "mode_boolean_product", "question": f"失效模式“{mode}”是否来自产品“{product}”？", "row_index": row_index} if product else {},
                {"kind": "mode_boolean_rpn", "question": f"失效模式“{mode}”的RPN是否为“{rpn}”？", "row_index": row_index} if rpn else {},
                {"kind": "mode_boolean_s", "question": f"失效模式“{mode}”的严酷度是否为“{s_val}”？", "row_index": row_index} if s_val else {},
                {"kind": "mode_boolean_o", "question": f"失效模式“{mode}”的发生度是否为“{o_val}”？", "row_index": row_index} if o_val else {},
                {"kind": "mode_boolean_d", "question": f"失效模式“{mode}”的可探测度是否为“{d_val}”？", "row_index": row_index} if d_val else {},
                {"kind": "mode_has_prevent", "question": f"失效模式“{mode}”是否记录了现行预防控制？", "row_index": row_index},
                {"kind": "mode_has_detect", "question": f"失效模式“{mode}”是否记录了现行探测控制？", "row_index": row_index},
            ]
        )
        if prevent:
            items.append({"kind": "mode_boolean_prevent", "question": f"失效模式“{mode}”的现行预防控制是否为“{prevent}”?", "row_index": row_index})
        if detect:
            items.append({"kind": "mode_boolean_detect", "question": f"失效模式“{mode}”的现行探测控制是否为“{detect}”？", "row_index": row_index})
        if action:
            items.append({"kind": "mode_boolean_action", "question": f"失效模式“{mode}”的建议措施是否为“{action}”？", "row_index": row_index})
        if fid:
            items.append({"kind": "code_to_mode", "question": f"FMEA编号“{fid}”对应的失效模式是什么？", "row_index": row_index})
        if project:
            items.append({"kind": "mode_project_repeat", "question": f"项目/功能“{project}”中是否包含失效模式“{mode}”？", "row_index": row_index})

    return [x for x in items if x]


def _project_questions(df: pd.DataFrame) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for project, sub in df.groupby("项目/功能", sort=False):
        project = _s(project)
        if not project:
            continue
        modes = [_s(x) for x in sub["潜在失效模式"].tolist() if _s(x)]
        effects = [_s(x) for x in sub["潜在失效后果"].tolist() if _s(x)]
        causes = [_s(x) for x in sub["潜在失效原因/机理"].tolist() if _s(x)]
        prevents = [_s(x) for x in sub["现行预防控制"].tolist() if _s(x)]
        detects = [_s(x) for x in sub["现行探测控制"].tolist() if _s(x)]
        actions = [_s(x) for x in sub["建议措施"].tolist() if _s(x)]
        max_mode = _s(sub.sort_values("风险优先数(RPN)", ascending=False).iloc[0]["潜在失效模式"])
        min_mode = _s(sub.sort_values("风险优先数(RPN)", ascending=True).iloc[0]["潜在失效模式"])
        max_rpn = int(sub["风险优先数(RPN)"].max())
        min_rpn = int(sub["风险优先数(RPN)"].min())

        items.extend(
            [
                {"kind": "project_modes", "question": f"项目/功能“{project}”包含哪些潜在失效模式？", "row_index": int(sub.index[0])},
                {"kind": "project_count", "question": f"项目/功能“{project}”共有多少条失效模式记录？", "row_index": int(sub.index[0])},
                {"kind": "project_avg_rpn", "question": f"项目/功能“{project}”的平均RPN是多少？", "row_index": int(sub.index[0])},
                {"kind": "project_max_rpn_mode", "question": f"项目/功能“{project}”中RPN最高的失效模式是什么？", "row_index": int(sub.index[0])},
                {"kind": "project_min_rpn_mode", "question": f"项目/功能“{project}”中RPN最低的失效模式是什么？", "row_index": int(sub.index[0])},
                {"kind": "project_max_rpn_value", "question": f"项目/功能“{project}”的最高RPN值是多少？", "row_index": int(sub.index[0])},
                {"kind": "project_min_rpn_value", "question": f"项目/功能“{project}”的最低RPN值是多少？", "row_index": int(sub.index[0])},
                {"kind": "project_avg_s", "question": f"项目/功能“{project}”的平均严酷度S是多少？", "row_index": int(sub.index[0])},
                {"kind": "project_avg_o", "question": f"项目/功能“{project}”的平均发生度O是多少？", "row_index": int(sub.index[0])},
                {"kind": "project_avg_d", "question": f"项目/功能“{project}”的平均可探测度D是多少？", "row_index": int(sub.index[0])},
                {"kind": "project_effects", "question": f"项目/功能“{project}”涉及哪些潜在失效后果？", "row_index": int(sub.index[0])},
                {"kind": "project_causes", "question": f"项目/功能“{project}”涉及哪些潜在失效原因/机理？", "row_index": int(sub.index[0])},
                {"kind": "project_prevents", "question": f"项目/功能“{project}”中出现过哪些现行预防控制？", "row_index": int(sub.index[0])},
                {"kind": "project_detects", "question": f"项目/功能“{project}”中出现过哪些现行探测控制？", "row_index": int(sub.index[0])},
                {"kind": "project_actions", "question": f"项目/功能“{project}”中出现过哪些建议措施？", "row_index": int(sub.index[0])},
                {"kind": "project_safety_count", "question": f"项目/功能“{project}”中后果为“安全事故”的失效模式有多少项？", "row_index": int(sub.index[0])},
                {"kind": "project_user_count", "question": f"项目/功能“{project}”中后果包含“影响用户使用”的失效模式有多少项？", "row_index": int(sub.index[0])},
                {"kind": "project_has_mode", "question": f"项目/功能“{project}”中是否包含失效模式“{max_mode}”？", "row_index": int(sub.index[0])} if max_mode else {},
                {"kind": "project_has_effect", "question": f"项目/功能“{project}”中是否出现过失效后果“{effects[0]}”？", "row_index": int(sub.index[0])} if effects else {},
                {"kind": "project_has_cause", "question": f"项目/功能“{project}”中是否出现过失效原因“{causes[0]}”？", "row_index": int(sub.index[0])} if causes else {},
                {"kind": "project_threshold_high", "question": f"项目/功能“{project}”中RPN不低于100的失效模式有哪些？", "row_index": int(sub.index[0])},
                {"kind": "project_threshold_low", "question": f"项目/功能“{project}”中RPN不高于90的失效模式有哪些？", "row_index": int(sub.index[0])},
                {"kind": "project_max_mode_boolean", "question": f"项目/功能“{project}”中RPN最高的失效模式是否为“{max_mode}”？", "row_index": int(sub.index[0])} if max_mode else {},
                {"kind": "project_min_mode_boolean", "question": f"项目/功能“{project}”中RPN最低的失效模式是否为“{min_mode}”？", "row_index": int(sub.index[0])} if min_mode else {},
                {"kind": "project_max_rpn_boolean", "question": f"项目/功能“{project}”的最高RPN是否为“{max_rpn}”？", "row_index": int(sub.index[0])},
                {"kind": "project_min_rpn_boolean", "question": f"项目/功能“{project}”的最低RPN是否为“{min_rpn}”？", "row_index": int(sub.index[0])},
            ]
        )
    return [x for x in items if x]


def _pair_questions(df: pd.DataFrame) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    projects = [_s(x) for x in df["项目/功能"].dropna().unique().tolist() if _s(x)]
    for i in range(len(projects)):
        for j in range(i + 1, len(projects)):
            a = projects[i]
            b = projects[j]
            items.extend(
                [
                    {"kind": "compare_avg_rpn", "question": f"项目/功能“{a}”和“{b}”相比，哪个平均RPN更高？", "row_index": 0},
                    {"kind": "compare_count", "question": f"项目/功能“{a}”和“{b}”相比，哪个包含的失效模式更多？", "row_index": 0},
                    {"kind": "compare_max_rpn", "question": f"项目/功能“{a}”和“{b}”中，哪个项目的最高RPN更大？", "row_index": 0},
                    {"kind": "compare_safety", "question": f"项目/功能“{a}”和“{b}”中，哪个项目包含更多后果为“安全事故”的失效模式？", "row_index": 0},
                    {"kind": "compare_detect", "question": f"项目/功能“{a}”和“{b}”中，哪个项目的平均可探测度D更高？", "row_index": 0},
                    {"kind": "compare_occurrence", "question": f"项目/功能“{a}”和“{b}”中，哪个项目的平均发生度O更高？", "row_index": 0},
                ]
            )
    return items


def _global_questions(df: pd.DataFrame) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    all_modes = [_s(x) for x in df["潜在失效模式"].tolist() if _s(x)]
    all_effects = [_s(x) for x in df["潜在失效后果"].tolist() if _s(x)]
    all_causes = [_s(x) for x in df["潜在失效原因/机理"].tolist() if _s(x)]
    all_projects = [_s(x) for x in df["项目/功能"].tolist() if _s(x)]
    all_prevents = [_s(x) for x in df["现行预防控制"].tolist() if _s(x)]
    all_detects = [_s(x) for x in df["现行探测控制"].tolist() if _s(x)]
    all_actions = [_s(x) for x in df["建议措施"].tolist() if _s(x)]

    high_mode = _s(df.sort_values("风险优先数(RPN)", ascending=False).iloc[0]["潜在失效模式"])
    low_mode = _s(df.sort_values("风险优先数(RPN)", ascending=True).iloc[0]["潜在失效模式"])
    high_rpn = int(df["风险优先数(RPN)"].max())
    low_rpn = int(df["风险优先数(RPN)"].min())

    items.extend(
        [
            {"kind": "global_count_modes", "question": "这份FMECA表总共有多少条失效模式记录？", "row_index": 0},
            {"kind": "global_count_projects", "question": "这份FMECA表覆盖了多少个项目/功能？", "row_index": 0},
            {"kind": "global_top_rpn_mode", "question": "整张表中RPN最高的失效模式是什么？", "row_index": 0},
            {"kind": "global_low_rpn_mode", "question": "整张表中RPN最低的失效模式是什么？", "row_index": 0},
            {"kind": "global_top_rpn_value", "question": "整张表中的最高RPN值是多少？", "row_index": 0},
            {"kind": "global_low_rpn_value", "question": "整张表中的最低RPN值是多少？", "row_index": 0},
            {"kind": "global_avg_rpn", "question": "整张表的平均RPN是多少？", "row_index": 0},
            {"kind": "global_avg_s", "question": "整张表的平均严酷度S是多少？", "row_index": 0},
            {"kind": "global_avg_o", "question": "整张表的平均发生度O是多少？", "row_index": 0},
            {"kind": "global_avg_d", "question": "整张表的平均可探测度D是多少？", "row_index": 0},
            {"kind": "global_safety_modes", "question": "整张表中哪些失效模式的后果是“安全事故”？", "row_index": 0},
            {"kind": "global_user_modes", "question": "整张表中哪些失效模式的后果包含“影响用户使用”？", "row_index": 0},
            {"kind": "global_work_modes", "question": "整张表中哪些失效模式的后果包含“影响电池工作”？", "row_index": 0},
            {"kind": "global_protect_modes", "question": "整张表中哪些失效模式采用了“提高防护等级”作为现行预防控制？", "row_index": 0},
            {"kind": "global_bit_modes", "question": "整张表中哪些失效模式采用了“BIT机内测试”作为现行探测控制？", "row_index": 0},
            {"kind": "global_high_threshold", "question": "整张表中RPN不低于150的失效模式有哪些？", "row_index": 0},
            {"kind": "global_low_threshold", "question": "整张表中RPN不高于90的失效模式有哪些？", "row_index": 0},
            {"kind": "global_s10_modes", "question": "整张表中严酷度S等于10的失效模式有哪些？", "row_index": 0},
            {"kind": "global_d6_modes", "question": "整张表中可探测度D等于6的失效模式有哪些？", "row_index": 0},
            {"kind": "global_o2_modes", "question": "整张表中发生度O等于2的失效模式有哪些？", "row_index": 0},
            {"kind": "global_has_mode", "question": f"整张表中是否包含失效模式“{high_mode}”？", "row_index": 0} if high_mode else {},
            {"kind": "global_has_low_mode", "question": f"整张表中是否包含失效模式“{low_mode}”？", "row_index": 0} if low_mode else {},
            {"kind": "global_has_effect", "question": f"整张表中是否存在失效后果“{all_effects[0]}”？", "row_index": 0} if all_effects else {},
            {"kind": "global_has_cause", "question": f"整张表中是否存在失效原因“{all_causes[0]}”？", "row_index": 0} if all_causes else {},
            {"kind": "global_has_project", "question": f"整张表中是否包含项目/功能“{all_projects[0]}”？", "row_index": 0} if all_projects else {},
            {"kind": "global_has_prevent", "question": f"整张表中是否使用过现行预防控制“{all_prevents[0]}”？", "row_index": 0} if all_prevents else {},
            {"kind": "global_has_detect", "question": f"整张表中是否使用过现行探测控制“{all_detects[0]}”？", "row_index": 0} if all_detects else {},
            {"kind": "global_has_action", "question": f"整张表中是否使用过建议措施“{all_actions[0]}”？", "row_index": 0} if all_actions else {},
            {"kind": "global_top_mode_rpn_boolean", "question": f"整张表中RPN最高的失效模式是否为“{high_mode}”？", "row_index": 0} if high_mode else {},
            {"kind": "global_top_rpn_boolean", "question": f"整张表中的最高RPN是否为“{high_rpn}”？", "row_index": 0},
            {"kind": "global_low_rpn_boolean", "question": f"整张表中的最低RPN是否为“{low_rpn}”？", "row_index": 0},
        ]
    )
    return [x for x in items if x]


def build_questions(df: pd.DataFrame, total: int = 500) -> list[dict[str, object]]:
    raw: list[dict[str, str]] = []
    for row_index, row in df.reset_index(drop=True).iterrows():
        raw.extend(_row_questions(row, row_index))
    raw.extend(_project_questions(df))
    raw.extend(_pair_questions(df))
    raw.extend(_global_questions(df))

    uniq = _uniq_keep_order(raw)

    if len(uniq) < total:
        rows = list(df.to_dict(orient="records"))
        idx = 0
        while len(uniq) < total:
            row = rows[idx % len(rows)]
            mode = _s(row.get("潜在失效模式"))
            project = _s(row.get("项目/功能"))
            effect = _s(row.get("潜在失效后果"))
            cause = _s(row.get("潜在失效原因/机理"))
            variants = [
                {"kind": "mode_alt", "question": f"请说明失效模式“{mode}”在项目/功能“{project}”中的风险特征。", "row_index": idx % len(rows)} if mode and project else {},
                {"kind": "effect_alt", "question": f"如果关注失效模式“{mode}”，其对应后果“{effect}”是否需要优先处理？", "row_index": idx % len(rows)} if mode and effect else {},
                {"kind": "cause_alt", "question": f"从原因角度看，失效模式“{mode}”是否由“{cause}”触发？", "row_index": idx % len(rows)} if mode and cause else {},
            ]
            uniq = _uniq_keep_order(uniq + [x for x in variants if x])
            idx += 1

    out: list[dict[str, object]] = []
    for i, item in enumerate(uniq[:total], start=1):
        out.append({"idx": i, "kind": item["kind"], "question": item["question"], "row_index": int(item.get("row_index", -1))})
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate 500 diverse questions for the normalized LFP FMECA CSV.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="normalized FMECA csv path")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output jsonl path")
    parser.add_argument("--total", type=int, default=500, help="number of questions")
    args = parser.parse_args()

    df = pd.read_csv(args.csv).fillna("")
    questions = build_questions(df, total=max(1, int(args.total)))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in questions:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"csv={args.csv}")
    print(f"out={out_path}")
    print(f"total={len(questions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
