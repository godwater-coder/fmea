# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_scenario_ablation_experiment import (  # noqa: E402
    CSV_COLUMNS,
    DIFFICULTY_LABELS,
    KIND_LABELS,
    TAG_LABELS,
    append_log,
    group_summary_rows,
    load_jsonl,
    route_label,
    score_answer,
    summarize,
    write_csv,
    write_json,
    write_jsonl,
    write_report,
)


DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
DEFAULT_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


def load_csv_context(path: str | None) -> str:
    if not path:
        return ""
    csv_path = Path(path)
    return csv_path.read_text(encoding="utf-8-sig")


def ask_ollama(
    question: str,
    *,
    model: str,
    base_url: str,
    timeout: int,
    csv_context: str = "",
    num_ctx: int = 32768,
) -> str:
    if csv_context:
        prompt = (
            "你是一个独立的大语言模型。下面给出一份完整 CSV 表格，它是本题唯一允许使用的数据来源。\n"
            "不要使用知识图谱、RAG、数据库查询、外部检索或任何系统工具；只阅读这份 CSV 文本并回答问题。\n"
            "回答必须简短、直接，保留 CSV 中的原始 FMEA 编号、字段值、英文实体名称和数值。\n"
            "如果问题询问 RPN、S、O、D、失效原因、失效后果或建议措施，优先在 CSV 中定位对应行并原样回答。\n\n"
            "CSV表格开始：\n"
            f"{csv_context}\n"
            "CSV表格结束。\n\n"
            f"问题：{question}\n"
            "答案："
        )
    else:
        prompt = (
            "你是一个独立的大语言模型，不允许使用外部数据库、知识图谱、RAG、CSV表格或检索工具。\n"
            "只能根据题面和你已有的通用知识作答。\n"
            "如果题目询问具体 FMEA 编号、RPN、S/O/D、失效原因、失效后果或建议措施，而题面没有给出足够信息，"
            "也请尽量给出你认为最可能的直接答案；不要声称你调用了任何系统。\n"
            "回答要简短，保留题面中的原始编号、数值和实体名称。\n\n"
            f"问题：{question}\n"
            "答案："
        )
    resp = requests.post(
        f"{base_url.rstrip('/')}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0, "num_predict": 512, "num_ctx": num_ctx},
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    message = payload.get("message") if isinstance(payload, dict) else None
    if isinstance(message, dict):
        return str(message.get("content") or "").strip()
    return str(payload.get("response") or "").strip() if isinstance(payload, dict) else ""


def run_questions(
    questions: list[dict[str, Any]],
    answer_path: Path,
    *,
    model: str,
    base_url: str,
    timeout: int,
    csv_context: str = "",
    num_ctx: int = 32768,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    answer_path.parent.mkdir(parents=True, exist_ok=True)
    with answer_path.open("w", encoding="utf-8") as f:
        for i, question in enumerate(questions, start=1):
            start = time.perf_counter()
            try:
                answer = ask_ollama(
                    str(question.get("question") or ""),
                    model=model,
                    base_url=base_url,
                    timeout=timeout,
                    csv_context=csv_context,
                    num_ctx=num_ctx,
                )
                error = ""
            except Exception as exc:
                answer = ""
                error = str(exc)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            row = {
                **question,
                "answer": answer,
                "route": "pure_llm",
                "route_confidence": 1.0,
                "query_ir": {},
                "adjudication": {},
                "context": [csv_context] if csv_context else [],
                "context_raw": [csv_context] if csv_context else [],
                "answer_file": "",
                "elapsed_ms": elapsed_ms,
                "error": error,
            }
            rows.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            if i % 25 == 0 or i == len(questions):
                print(f"进度：{i}/{len(questions)}", flush=True)
    return rows


def write_config(path: Path, *, model: str, base_url: str, context_csv: str = "", num_ctx: int = 32768) -> dict[str, Any]:
    has_csv = bool(context_csv)
    payload = {
        "model_id": "PureLLM",
        "model_name": f"PureLLM表格上下文回答({model})" if has_csv else f"PureLLM直接回答({model})",
        "removed_module": "无KG/RAG/数据库/确定性规则系统",
        "description": (
            "不使用知识图谱、RAG、数据库查询、CSV直答、确定性规则或证据裁决；"
            "每题将完整 CSV 文本随 prompt 提供给本地 Ollama 大模型，由模型自行阅读表格并回答。"
            if has_csv
            else "不使用知识图谱、RAG、CSV直答、确定性规则或证据裁决，仅由本地 Ollama 大模型根据题面直接作答。"
        ),
        "llm_model": model,
        "ollama_base_url": base_url,
        "context_csv": context_csv,
        "num_ctx": num_ctx,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Pure LLM direct-answer comparison experiment.")
    parser.add_argument("--questions", required=True)
    parser.add_argument("--csv", default="无")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--context-csv", default="", help="作为 prompt 上下文发送给纯 LLM 的完整 CSV。")
    parser.add_argument("--num-ctx", type=int, default=32768, help="Ollama num_ctx，上下文窗口大小。")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "运行日志.log"
    log_path.write_text("", encoding="utf-8")

    generated_at = datetime.now().replace(microsecond=0).isoformat()
    csv_context = load_csv_context(args.context_csv)
    config = write_config(
        output_dir / "pure_llm_config.json",
        model=args.model,
        base_url=args.base_url,
        context_csv=args.context_csv,
        num_ctx=args.num_ctx,
    )
    model_id = str(config["model_id"])
    model_name = str(config["model_name"])
    removed_module = str(config["removed_module"])

    start_all = time.perf_counter()
    append_log(log_path, f"加载模型：{model_name}，对照组：{removed_module}")
    if csv_context:
        append_log(log_path, f"不初始化知识图谱，不使用检索；每题 prompt 附带完整 CSV：{args.context_csv}")
    else:
        append_log(log_path, "不初始化知识图谱，不导入 CSV，不使用检索。")

    questions = load_jsonl(Path(args.questions))
    answer_rows = run_questions(
        questions,
        output_dir / "模型回答.jsonl",
        model=args.model,
        base_url=args.base_url,
        timeout=args.timeout,
        csv_context=csv_context,
        num_ctx=args.num_ctx,
    )
    append_log(log_path, f"完成请求：{len(answer_rows)}/{len(questions)}")

    detail_rows: list[dict[str, Any]] = []
    route_counts: Counter[str] = Counter()
    for seq, (q, payload) in enumerate(zip(questions, answer_rows), start=1):
        scored = score_answer(q, payload)
        answer = scored["answer"]
        route = route_label(payload, answer)
        if route == "pure_llm":
            route = "纯LLM直答"
        route_counts[route] += 1
        detail = {
            **q,
            **scored,
            "model_id": model_id,
            "model_name": model_name,
            "removed_module": removed_module,
            "route": payload.get("route", ""),
            "answer": answer,
            "elapsed_ms": float(payload.get("elapsed_ms") or 0.0),
            "error": payload.get("error", ""),
            "context": [],
            "context_raw": [],
            "query_ir": {},
            "adjudication": {},
            "序号": seq,
            "全局序号": int(q.get("global_idx") or q.get("idx") or seq),
            "消融模型": model_name,
            "去除模块": removed_module,
            "题型": KIND_LABELS.get(str(q.get("kind") or ""), str(q.get("kind") or "")),
            "来源标签": TAG_LABELS.get(str(q.get("tag") or ""), str(q.get("tag") or "")),
            "模块标签": q.get("module_label_name") or q.get("module_label", ""),
            "模块标签说明": q.get("module_label_note", ""),
            "难度": DIFFICULTY_LABELS.get(str(q.get("difficulty") or ""), str(q.get("difficulty") or "")),
            "问题": q.get("question", ""),
            "模型回答": answer,
            "是否正确": "正确" if scored["correct"] else "错误",
            "部分准确率": scored["partial"],
            "耗时毫秒": float(payload.get("elapsed_ms") or 0.0),
            "回答路径": route,
            "上下文精确率": scored["context_precision"],
            "证据召回率": scored["evidence_recall"],
            "幻觉标记": scored["hallucination"],
            "多跳路径覆盖率": scored["multi_hop_path_coverage"],
            "上下文条数": scored["context_count"],
            "缺失文本项": scored["missing_terms"],
            "缺失数值项": scored["missing_numbers"],
            "命中数值": scored["found_numbers"],
            "无证据编号": scored["unsupported_codes"],
            "无证据数值": scored["unsupported_numbers"],
            "标准文本项": q.get("expected_terms", []),
            "标准数值项": q.get("expected_numbers", []),
            "预期字段": q.get("expected_fields", []),
            "原始行号": q.get("row_index", ""),
            "错误信息": payload.get("error", ""),
        }
        detail_rows.append(detail)

    total_summary = summarize(detail_rows)
    groups = group_summary_rows(detail_rows)
    summary = {
        "消融模型": model_name,
        "模型编号": model_id,
        "去除模块": removed_module,
        "配置文件": str(output_dir / "pure_llm_config.json"),
        "生成时间": generated_at,
        "运行耗时秒": round(time.perf_counter() - start_all, 2),
        "总体指标": total_summary,
        "回答路径分布": dict(route_counts),
        "按情景类别统计": [
            {"分类": g["分类"], **{k: v for k, v in g.items() if k not in {"分组维度", "分类"}}}
            for g in groups
            if g["分组维度"] == "情景类别"
        ],
        "按模块标签统计": [
            {"分类": g["分类"], **{k: v for k, v in g.items() if k not in {"分组维度", "分类"}}}
            for g in groups
            if g["分组维度"] == "模块标签"
        ],
        "按题型统计": [
            {"分类": g["分类"], **{k: v for k, v in g.items() if k not in {"分组维度", "分类"}}}
            for g in groups
            if g["分组维度"] == "题型"
        ],
        "按来源标签统计": [
            {"分类": g["分类"], **{k: v for k, v in g.items() if k not in {"分组维度", "分类"}}}
            for g in groups
            if g["分组维度"] == "来源标签"
        ],
        "按难度统计": [
            {"分类": g["分类"], **{k: v for k, v in g.items() if k not in {"分组维度", "分类"}}}
            for g in groups
            if g["分组维度"] == "难度"
        ],
    }

    write_jsonl(output_dir / "逐题明细.jsonl", detail_rows)
    csv_rows = []
    for row in detail_rows:
        csv_row = row.copy()
        for key in ("缺失文本项", "缺失数值项", "命中数值", "无证据编号", "无证据数值", "标准文本项", "标准数值项", "预期字段"):
            value = csv_row.get(key)
            if isinstance(value, list):
                csv_row[key] = "；".join(str(x) for x in value)
        csv_rows.append(csv_row)
    write_csv(output_dir / "逐题明细.csv", csv_rows, CSV_COLUMNS)
    write_csv(
        output_dir / "分类汇总.csv",
        groups,
        [
            "分组维度",
            "分类",
            "题数",
            "正确题数",
            "完全准确率",
            "平均部分准确率",
            "平均耗时毫秒",
            "上下文精确率",
            "证据召回率",
            "幻觉率",
            "多跳路径覆盖率",
        ],
    )
    write_json(output_dir / "汇总指标.json", summary)
    write_json(output_dir / "使用题集.json", {"题集文件": args.questions, "题数": len(questions)})
    write_report(
        output_dir / "实验报告.md",
        model_name,
        removed_module,
        generated_at,
        args.csv,
        args.questions,
        0,
        False,
        total_summary,
        groups,
        route_counts,
        [r for r in detail_rows if not r["correct"]],
    )
    append_log(log_path, f"完成：完全准确率={total_summary['完全准确率']}，平均部分准确率={total_summary['平均部分准确率']}")
    print(json.dumps(total_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
