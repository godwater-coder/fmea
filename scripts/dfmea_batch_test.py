# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd
import requests


DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_CSV = Path("data/dfmea_final.csv")
DEFAULT_QUESTION_FILE = Path("answer/dfmea_100_questions.jsonl")
DEFAULT_ANSWER_FILE = Path("answer/dfmea_100_answers.jsonl")
DEFAULT_PROGRESS_FILE = Path("answer/dfmea_100_progress.jsonl")


@dataclass
class QaItem:
    idx: int
    question: str
    row_index: int
    kind: str


def _s(v: Any) -> str:
    if v is None:
        return ""
    if pd.isna(v):
        return ""
    return str(v).strip()


def _build_questions(df: pd.DataFrame, total: int = 100) -> list[QaItem]:
    rows = df.copy()
    if "设计项目" in rows.columns:
        rows["设计项目"] = rows["设计项目"].ffill()
        rows["设计项目"] = rows["设计项目"].map(_s)
    rows = rows.fillna("")
    items: list[QaItem] = []

    templates = [
        ("mode", "设计项目“{proj}”对应的潜在失效模式有哪些？"),
        ("cause", "失效模式“{mode}”的潜在失效原因/机理是什么？"),
        ("effect", "失效模式“{mode}”的潜在失效后果是什么？"),
        ("controls", "针对失效模式“{mode}”，现行预防性设计控制和探测性设计控制分别是什么？"),
        ("rpn", "失效模式“{mode}”的RPN是多少？"),
        ("s", "失效模式“{mode}”的严重度是多少？"),
        ("o", "失效模式“{mode}”的频度数是多少？"),
        ("d", "失效模式“{mode}”的探测度数是多少？"),
        ("avg", "设计项目“{proj}”的平均RPN是多少？"),
        ("max", "设计项目“{proj}”中RPN最高的失效模式是什么？"),
    ]

    for i in range(total):
        row = rows.iloc[i % len(rows)]
        proj = _s(row.get("设计项目"))
        mode = _s(row.get("潜在的失效模式"))
        effect = _s(row.get("潜在的失效后果"))
        cause = _s(row.get("潜在的失效原因/机理"))
        kind, tpl = templates[i % len(templates)]

        question = tpl.format(proj=proj or "该项目", mode=mode or "该失效模式")
        if kind == "cause" and cause:
            question = f'失效模式“{mode}”对应的原因是否包含“{cause.split()[0]}”？'
        if kind == "effect" and effect:
            question = f'失效模式“{mode}”的后果是否为“{effect}”？'

        items.append(QaItem(idx=i + 1, question=question, row_index=i % len(rows), kind=kind))

    return items


def _write_questions(path: Path, items: list[QaItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item.__dict__, ensure_ascii=False) + "\n")


def _load_questions(path: Path) -> list[QaItem]:
    items: list[QaItem] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            items.append(
                QaItem(
                    idx=int(row["idx"]),
                    question=str(row["question"]),
                    row_index=int(row["row_index"]),
                    kind=str(row["kind"]),
                )
            )
    return items


def _call_api(base_url: str, question: str, timeout: int = 180) -> dict[str, Any]:
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/v1/question-answer",
        json={"question": question},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def _write_answers(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_progress(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate 100 dfmea questions and batch test the QA API.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="dfmea csv path")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="backend base url")
    parser.add_argument("--questions", default=str(DEFAULT_QUESTION_FILE), help="output question file")
    parser.add_argument("--answers", default=str(DEFAULT_ANSWER_FILE), help="output answer file")
    parser.add_argument("--progress", default=str(DEFAULT_PROGRESS_FILE), help="progress jsonl file")
    parser.add_argument("--total", type=int, default=100, help="number of questions")
    parser.add_argument("--workers", type=int, default=8, help="concurrent request workers")
    parser.add_argument("--timeout", type=int, default=30, help="per-request timeout seconds")
    parser.add_argument("--reuse-questions", action="store_true", help="reuse existing question file instead of regenerating")
    args = parser.parse_args()

    question_path = Path(args.questions)
    answer_path = Path(args.answers)
    progress_path = Path(args.progress)
    if args.reuse_questions:
        items = _load_questions(question_path)
    else:
        df = pd.read_csv(args.csv)
        items = _build_questions(df, total=args.total)
        _write_questions(question_path, items)

    results: list[dict[str, Any]] = []
    progress_rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {executor.submit(_call_api, args.base_url, item.question, args.timeout): item for item in items}
        done = 0
        for future in as_completed(futures):
            item = futures[future]
            done += 1
            try:
                payload = future.result()
                row = {
                    "idx": item.idx,
                    "kind": item.kind,
                    "question": item.question,
                    "answer": payload.get("answer", ""),
                    "context": payload.get("context", []),
                    "answer_file": payload.get("answer_file", ""),
                    "error": "",
                }
            except Exception as e:
                row = {
                    "idx": item.idx,
                    "kind": item.kind,
                    "question": item.question,
                    "answer": "",
                    "context": [],
                    "answer_file": "",
                    "error": str(e),
                }
            results.append(row)
            progress_rows.append({
                "done": done,
                "total": len(items),
                "idx": item.idx,
                "kind": item.kind,
                "question": item.question,
                "ok": not bool(row.get("error")),
            })
            _write_progress(progress_path, progress_rows)
            print(f"[{done}/{len(items)}] {item.kind}: {item.question[:40]}", flush=True)

    _write_answers(answer_path, results)
    print(f"questions={question_path}")
    print(f"answers={answer_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
