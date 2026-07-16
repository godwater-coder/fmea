# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import pandas as pd
from score_dfmea_qa import score_compare_row


DEFAULT_CSV = Path("data/dfmea_final.csv")
DEFAULT_QUESTIONS = Path("answer/dfmea_100_questions.jsonl")
DEFAULT_PREDICTIONS = Path("answer/dfmea_100_answers.jsonl")
DEFAULT_OUTPUT = Path("answer/dfmea_100_qa_compare.csv")
DEFAULT_GOLD_ONLY_OUTPUT = Path("answer/dfmea_100_question_gold.csv")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def s(v: Any) -> str:
    if v is None:
        return ""
    if pd.isna(v):
        return ""
    return str(v).strip()


def make_df(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path).copy()
    if "设计项目" in df.columns:
        df["设计项目"] = df["设计项目"].ffill()
        df["设计项目"] = df["设计项目"].map(lambda x: s(x))
    return df


def unique_nonempty(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        x = s(v)
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def gold_answer(df: pd.DataFrame, row_index: int, kind: str) -> str:
    row = df.iloc[row_index]
    project = s(row.get("设计项目"))
    mode = s(row.get("潜在的失效模式"))
    effect = s(row.get("潜在的失效后果"))
    cause = s(row.get("潜在的失效原因/机理"))
    prev = s(row.get("现行预防性设计控制"))
    det = s(row.get("现行探测性设计控制"))
    sev = s(row.get("严重度"))
    occ = s(row.get("频度数"))
    det_num = s(row.get("探测度数"))
    rpn = s(row.get("RPN"))

    project_rows = df[df["设计项目"] == project] if project else df.iloc[0:0]
    project_modes = unique_nonempty(project_rows["潜在的失效模式"].tolist()) if len(project_rows) else []
    project_rpn = pd.to_numeric(project_rows["RPN"], errors="coerce") if len(project_rows) else pd.Series([], dtype=float)

    if kind == "mode":
        if project_modes:
            return f"{project}对应的潜在失效模式包括：" + "，".join(project_modes)
        return "无"
    if kind == "cause":
        return f"失效模式“{mode}”的潜在失效原因/机理是：{cause}。"
    if kind == "effect":
        return f"失效模式“{mode}”的潜在失效后果是：{effect}。"
    if kind == "controls":
        return f"针对“{mode}”，现行预防性设计控制是：{prev or '无'}；现行探测性设计控制是：{det or '无'}。"
    if kind == "rpn":
        return f"失效模式“{mode}”的RPN是：{rpn}。"
    if kind == "s":
        return f"失效模式“{mode}”的严重度(S)是：{sev}。"
    if kind == "o":
        return f"失效模式“{mode}”的频度数(O)是：{occ}。"
    if kind == "d":
        return f"失效模式“{mode}”的探测度数(D)是：{det_num}。"
    if kind == "avg":
        if len(project_rpn):
            return f"设计项目“{project}”的平均RPN是：{project_rpn.mean():.2f}。"
        return f"设计项目“{project}”无可计算的RPN。"
    if kind == "max":
        if len(project_rpn):
            max_rpn = float(project_rpn.max())
            modes = unique_nonempty(project_rows.loc[pd.to_numeric(project_rows["RPN"], errors="coerce") == max_rpn, "潜在的失效模式"].tolist())
            return f"设计项目“{project}”中RPN最高的失效模式是：" + "，".join(modes) + f"；RPN={max_rpn:.0f}。"
        return f"设计项目“{project}”无可计算的RPN。"
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Export question/answer/gold-answer comparison file for dfmea QA.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV))
    parser.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    parser.add_argument("--predictions", default=str(DEFAULT_PREDICTIONS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--gold-only-output", default=str(DEFAULT_GOLD_ONLY_OUTPUT))
    parser.add_argument("--fill-missing-answer", action="store_true")
    args = parser.parse_args()

    df = make_df(Path(args.csv))
    questions = load_jsonl(Path(args.questions))
    predictions_path = Path(args.predictions)
    predictions = {int(x["idx"]): x for x in load_jsonl(predictions_path)} if predictions_path.exists() else {}
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gold_only_path = Path(args.gold_only_output)
    gold_only_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["idx", "kind", "question", "raw_answer", "answer", "gold_answer", "score", "correct", "detail"],
        )
        writer.writeheader()
        for q in questions:
            idx = int(q["idx"])
            raw_answer = str((predictions.get(idx) or {}).get("answer") or "")
            gold = gold_answer(df, int(q["row_index"]), str(q["kind"]))
            answer = raw_answer or (gold if args.fill_missing_answer else "")
            scored = score_compare_row(
                {
                    "idx": idx,
                    "kind": str(q["kind"]),
                    "question": str(q["question"]),
                    "answer": answer,
                    "gold_answer": gold,
                }
            )
            writer.writerow(
                {
                    "idx": idx,
                    "kind": str(q["kind"]),
                    "question": str(q["question"]),
                    "raw_answer": raw_answer,
                    "answer": answer,
                    "gold_answer": gold,
                    "score": scored.get("score", 0.0),
                    "correct": "yes" if int(scored.get("score", 0) or 0) == 1 else "no",
                    "detail": scored.get("detail", ""),
                }
            )

    with gold_only_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["idx", "kind", "question", "gold_answer"],
        )
        writer.writeheader()
        for q in questions:
            writer.writerow(
                {
                    "idx": int(q["idx"]),
                    "kind": str(q["kind"]),
                    "question": str(q["question"]),
                    "gold_answer": gold_answer(df, int(q["row_index"]), str(q["kind"])),
                }
            )

    print(out_path)
    print(gold_only_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
