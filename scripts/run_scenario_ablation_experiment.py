# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

import requests


PUNCT_RE = re.compile(r"[\s\u3000，。！？；：、,.!?;:\"'“”‘’（）()\[\]{}<>《》\-_/\\|]+")
NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")
QUOTE_RE = re.compile(r"[“\"‘']([^”\"’']+)[”\"’']")


KIND_LABELS = {
    "cause_effect_action_recommendation": "原因后果查建议措施",
    "cause_effect_to_sod_rpn": "原因后果查风险指标",
    "cause_mode_prevention_action": "原因失效现象查预防措施",
    "cause_mode_to_sod_rpn": "原因失效现象查风险指标",
    "cause_to_action_no_id": "原因查措施",
    "effect_cause_to_action": "后果原因查措施",
    "effect_detection_to_cause": "后果探测度查原因",
    "effect_to_action_no_id": "后果查措施",
    "mode_effect_action": "失效现象后果查处置建议",
    "mode_effect_rpn_to_cause": "失效现象后果风险查原因",
    "mode_effect_to_rpn": "失效现象后果查RPN",
    "mode_full_risk_profile": "失效现象查完整风险画像",
    "mode_rpn_action": "失效现象风险分查措施",
    "project_action_recommendation": "项目失效现象查改进动作",
    "project_cause_to_effect_rpn": "项目原因查后果与RPN",
    "project_mode_effect_rpn": "项目失效现象查后果与RPN",
    "project_mode_effect_to_cause": "项目失效现象后果查原因",
    "project_mode_occurrence_to_cause": "项目失效现象发生度查原因",
    "project_mode_rpn_to_action": "项目失效现象风险查措施",
    "project_mode_sod_to_cause": "项目失效现象风险指标查原因",
    "project_mode_to_action": "项目失效现象查措施",
    "project_mode_to_effect": "项目失效现象查后果",
    "risk_profile_to_action": "风险画像查措施",
}

TAG_LABELS = {
    "cause_action_reasoning": "原因到措施推理",
    "effect_action_reasoning": "后果到措施推理",
    "effect_cause_reasoning": "后果到原因推理",
    "fault_action_lookup": "故障措施查询",
    "fault_cause_lookup": "故障原因查询",
    "project_scoped_action": "项目范围措施查询",
    "project_scoped_cause": "项目范围原因查询",
    "project_scoped_risk": "项目范围风险评估",
    "risk_effect_lookup": "风险后果查询",
    "risk_effect_metric": "后果与风险指标查询",
    "risk_metric_lookup": "风险指标查询",
    "risk_profile": "完整风险画像",
}

DIFFICULTY_LABELS = {"easy": "简单", "medium": "中等", "hard": "困难"}

CSV_COLUMNS = [
    "序号",
    "全局序号",
    "消融模型",
    "去除模块",
    "情景类别",
    "题型",
    "来源标签",
    "模块标签",
    "模块标签说明",
    "难度",
    "问题",
    "参考答案",
    "模型回答",
    "是否正确",
    "部分准确率",
    "耗时毫秒",
    "回答路径",
    "路由命中",
    "槽位命中",
    "裁决状态",
    "缺失槽位",
    "拒答正确",
    "可追溯",
    "上下文精确率",
    "证据召回率",
    "幻觉标记",
    "多跳路径覆盖率",
    "上下文条数",
    "缺失文本项",
    "缺失数值项",
    "命中数值",
    "无证据编号",
    "无证据数值",
    "标准文本项",
    "标准数值项",
    "预期字段",
    "原始行号",
    "错误信息",
]


def norm_text(text: Any) -> str:
    s = "" if text is None else str(text)
    return PUNCT_RE.sub("", s.strip().lower())


def contains_term(text: Any, term: Any) -> bool:
    t = norm_text(text)
    s = norm_text(term)
    return bool(t and s and s in t)


def extract_numbers(text: Any) -> list[float]:
    out: list[float] = []
    for raw in NUM_RE.findall("" if text is None else str(text)):
        try:
            out.append(float(raw))
        except ValueError:
            pass
    return out


def number_match(value: float, values: list[float], tol: float = 1e-2) -> bool:
    return any(abs(float(value) - float(v)) <= tol for v in values)


def extract_quoted(text: Any) -> list[str]:
    return [x.strip() for x in QUOTE_RE.findall("" if text is None else str(text)) if x.strip()]


def infer_boolean_answer(text: Any) -> bool | None:
    answer = str(text or "").strip()
    if not answer:
        return None
    negative_patterns = ("不是", "不属于", "不包含", "不为", "否", "没有", "不存在", "未记录", "无证据", "证据不足")
    positive_patterns = ("是", "属于", "包含", "为", "存在", "记录了", "有")
    for pattern in negative_patterns:
        if pattern in answer:
            return False
    for pattern in positive_patterns:
        if pattern in answer:
            return True
    return None


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _safe_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def context_texts(payload: dict[str, Any]) -> list[str]:
    context = payload.get("context")
    if isinstance(context, list):
        texts = [_safe_text(x) for x in context if str(x).strip()]
        if texts:
            return texts
    raw = payload.get("context_raw")
    if isinstance(raw, list):
        return [_safe_text(x) for x in raw if str(x).strip()]
    if raw:
        return [_safe_text(raw)]
    return []


def route_label(payload: dict[str, Any], answer: str) -> str:
    if "待确认" in answer or "证据不足" in answer:
        return "拒答/证据不足"
    route = str(payload.get("route") or "").strip()
    if route == "csv_basic":
        return "CSV直答"
    if route == "deterministic_rule":
        return "确定性规则问答"
    if route in {"semantic_rag", "vector"}:
        return "语义RAG"
    if route in {"structured", "graph"}:
        return "QueryIR结构化查询"
    if route in {"reject", "pending"}:
        return "拒答/证据不足"
    return route or "未知路径"


def score_answer(question: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    answer = str(payload.get("answer") or "")
    if "expected_bool" in question:
        expected_bool = bool(question.get("expected_bool"))
        predicted_bool = infer_boolean_answer(answer)
        contexts = context_texts(payload)
        merged_context = "\n".join(contexts)
        quoted_terms = [x for x in extract_quoted(question.get("question", "")) if len(norm_text(x)) >= 2]
        if not quoted_terms:
            quoted_terms = [str(x).strip() for x in question.get("expected_terms") or [] if str(x).strip()]
        relevant_contexts = sum(1 for c in contexts if any(contains_term(c, t) for t in quoted_terms))
        context_precision = round(relevant_contexts / len(contexts), 4) if contexts else None
        labels = question.get("labels") or []
        multi_hop = "multi_hop" in labels
        return {
            "answer": answer,
            "correct": int(predicted_bool is not None and predicted_bool == expected_bool),
            "partial": 1.0 if (predicted_bool is not None and predicted_bool == expected_bool) else 0.0,
            "missing_terms": [] if predicted_bool is not None and predicted_bool == expected_bool else ["是/否判断"],
            "missing_numbers": [],
            "found_numbers": [],
            "context_count": len(contexts),
            "context_precision": context_precision,
            "evidence_recall": context_precision,
            "hallucination": int(predicted_bool is None),
            "unsupported_codes": [],
            "unsupported_numbers": [],
            "multi_hop_path_coverage": context_precision if multi_hop else None,
        }

    expected_terms = [str(x).strip() for x in question.get("expected_terms") or [] if str(x).strip()]
    expected_numbers = [float(x) for x in question.get("expected_numbers") or []]
    answer_numbers = extract_numbers(answer)

    matched_terms = [t for t in expected_terms if contains_term(answer, t)]
    missing_terms = [t for t in expected_terms if t not in matched_terms]
    matched_numbers = [n for n in expected_numbers if number_match(n, answer_numbers)]
    missing_numbers = [n for n in expected_numbers if not number_match(n, answer_numbers)]

    required = len(expected_terms) + len(expected_numbers)
    matched = len(matched_terms) + len(matched_numbers)
    partial = round(matched / required, 4) if required else 0.0
    correct = int(required > 0 and matched == required)

    contexts = context_texts(payload)
    merged_context = "\n".join(contexts)
    quoted_terms = [x for x in extract_quoted(question.get("question", "")) if len(norm_text(x)) >= 2]
    if not quoted_terms:
        quoted_terms = expected_terms
    relevant_contexts = sum(1 for c in contexts if any(contains_term(c, t) for t in quoted_terms))
    context_precision = round(relevant_contexts / len(contexts), 4) if contexts else None

    evidence_required = len(expected_terms) + len(expected_numbers)
    evidence_hits = sum(1 for t in expected_terms if contains_term(merged_context, t))
    context_numbers = extract_numbers(merged_context)
    evidence_hits += sum(1 for n in expected_numbers if number_match(n, context_numbers))
    evidence_recall = round(evidence_hits / evidence_required, 4) if evidence_required else None

    expected_ref_numbers = extract_numbers(question.get("参考答案", "")) + extract_numbers(expected_terms)
    question_numbers = extract_numbers(question.get("question", ""))
    allowed_numbers = expected_numbers + expected_ref_numbers + question_numbers + context_numbers
    unsupported_numbers = [n for n in answer_numbers if not number_match(n, allowed_numbers)]
    hallucination = int(bool(unsupported_numbers))

    labels = question.get("labels") or []
    multi_hop = "multi_hop" in labels
    multi_hop_coverage = evidence_recall if multi_hop else None

    found_reference_numbers = [
        n for n in answer_numbers if number_match(n, expected_ref_numbers + expected_numbers)
    ]
    unsupported_codes = [
        code
        for code in re.findall(r"\b[A-Z]{1,4}\d{1,4}\b", answer)
        if code not in str(question.get("question", "")) and code not in merged_context
    ]

    return {
        "answer": answer,
        "correct": correct,
        "partial": partial,
        "missing_terms": missing_terms,
        "missing_numbers": missing_numbers,
        "found_numbers": found_reference_numbers,
        "context_count": len(contexts),
        "context_precision": context_precision,
        "evidence_recall": evidence_recall,
        "hallucination": hallucination,
        "unsupported_codes": unsupported_codes,
        "unsupported_numbers": unsupported_numbers,
        "multi_hop_path_coverage": multi_hop_coverage,
    }


def avg(values: list[Any]) -> float | None:
    nums = [float(v) for v in values if v is not None and str(v) != ""]
    return round(mean(nums), 4) if nums else None


def avg_ms(values: list[Any]) -> float:
    nums = [float(v) for v in values if v is not None and str(v) != ""]
    return round(mean(nums), 2) if nums else 0.0


def _normalized_route(route: Any) -> str:
    value = str(route or "").strip()
    return "semantic_rag" if value in {"vector", "semantic_rag"} else value


def route_hit(question: dict[str, Any], payload: dict[str, Any]) -> int | None:
    expected = question.get("expected_route") or question.get("expected_routes")
    if not expected:
        module = str(question.get("module_eval_target") or "")
        expected = {"M1": ["csv_basic"], "M2": ["deterministic_rule"], "M3": ["semantic_rag"]}.get(module)
    if not expected:
        return None
    if isinstance(expected, str):
        expected = [expected]
    actual = _normalized_route(payload.get("route"))
    return int(actual in {_normalized_route(x) for x in expected})


def slot_hit(question: dict[str, Any], payload: dict[str, Any]) -> int | None:
    ir = payload.get("query_ir") or {}
    checks: list[bool] = []
    expected_intent = str(question.get("expected_intent") or "").strip()
    if expected_intent:
        checks.append(str(ir.get("intent") or "") == expected_intent)
    expected_metric = str(question.get("expected_metric") or "").strip()
    if expected_metric:
        checks.append(str(ir.get("metric") or "") == expected_metric)
    expected_entities = question.get("expected_entities") or []
    actual_entities = {str(x.get("value") or "") for x in (ir.get("entities") or []) if isinstance(x, dict)}
    for entity in expected_entities:
        value = str(entity.get("value") if isinstance(entity, dict) else entity)
        if value:
            checks.append(value in actual_entities)
    expected_constraints = question.get("expected_constraints") or []
    actual_constraints = ir.get("constraints") or []
    for constraint in expected_constraints:
        checks.append(constraint in actual_constraints)
    return int(all(checks)) if checks else None


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    adjudication_counts = Counter(str(r.get("adjudication_status") or "none") for r in rows)
    return {
        "题数": len(rows),
        "正确题数": int(sum(int(r["correct"]) for r in rows)),
        "完全准确率": round(mean([float(r["correct"]) for r in rows]) if rows else 0.0, 4),
        "平均部分准确率": avg([r["partial"] for r in rows]) or 0.0,
        "平均耗时毫秒": avg_ms([r["elapsed_ms"] for r in rows]),
        "上下文精确率": avg([r["context_precision"] for r in rows]),
        "证据召回率": avg([r["evidence_recall"] for r in rows]),
        "幻觉率": avg([r["hallucination"] for r in rows]) or 0.0,
        "多跳路径覆盖率": avg([r["multi_hop_path_coverage"] for r in rows]),
        "路由命中率": avg([r.get("route_hit") for r in rows]),
        "槽位解析命中率": avg([r.get("slot_hit") for r in rows]),
        "可追溯率": avg([r.get("traceable") for r in rows]),
        "拒答正确率": avg([r.get("rejection_correct") for r in rows]),
        "裁决状态分布": dict(adjudication_counts),
    }


def group_summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    specs = [
        ("模块标签", lambda r: r.get("模块标签", "")),
        ("情景类别", lambda r: r["情景类别"]),
        ("题型", lambda r: r["题型"]),
        ("来源标签", lambda r: r["来源标签"]),
        ("难度", lambda r: r["难度"]),
    ]
    out: list[dict[str, Any]] = []
    for dim, getter in specs:
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            buckets[str(getter(row) or "")].append(row)
        for key in sorted(buckets):
            s = summarize(buckets[key])
            out.append({"分组维度": dim, "分类": key, **s})
    return out


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def report_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("| " + " | ".join(["---"] + ["---:"] * (len(headers) - 1)) + " |")
    for row in rows:
        lines.append("| " + " | ".join("" if x is None else str(x) for x in row) + " |")
    return "\n".join(lines)


def write_report(
    path: Path,
    model_name: str,
    removed_module: str,
    generated_at: str,
    csv_path: str,
    question_path: str,
    top_k: int,
    rebuild_graph: bool,
    total_summary: dict[str, Any],
    groups: list[dict[str, Any]],
    route_counts: Counter[str],
    error_rows: list[dict[str, Any]],
) -> None:
    scenario_rows = [
        g for g in groups if g["分组维度"] == "情景类别"
    ]
    lines = [
        f"# {model_name} 实验报告",
        "",
        f"去除模块：{removed_module}",
        f"生成时间：{generated_at}",
        "",
        "## 实验配置",
        "",
        f"- 数据集：`{csv_path}`",
        f"- 题集：`{question_path}`",
        "- 生成模型：`qwen2.5:7b`",
        "- Embedding 模型：`nomic-embed-text`",
        "- 温度：0",
        f"- top_k：{top_k}",
        f"- 是否重建图谱：{rebuild_graph}",
        "",
        "## 总体指标",
        "",
        report_table(
            ["指标", "数值"],
            [[k, v] for k, v in total_summary.items()],
        ),
        "",
        "## 按情景类别统计",
        "",
        report_table(
            [
                "情景类别",
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
            [
                [
                    g["分类"],
                    g["题数"],
                    g["正确题数"],
                    g["完全准确率"],
                    g["平均部分准确率"],
                    g["平均耗时毫秒"],
                    g["上下文精确率"],
                    g["证据召回率"],
                    g["幻觉率"],
                    g["多跳路径覆盖率"],
                ]
                for g in scenario_rows
            ],
        ),
        "",
        "## 回答路径分布",
        "",
        report_table(["回答路径", "题数"], [[k, v] for k, v in route_counts.most_common()]),
    ]
    if error_rows:
        lines.extend(["", "## 错误样例", ""])
        for row in error_rows[:20]:
            q = str(row.get("问题", ""))[:160]
            a = str(row.get("模型回答", ""))[:180].replace("\n", " ")
            lines.append(f"- #{row['序号']} 得分={row['部分准确率']} 情景={row['情景类别']} 问题：{q}；回答：{a}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def post_json(base_url: str, path: str, payload: dict[str, Any], timeout: int = 1800) -> Any:
    resp = requests.post(f"{base_url.rstrip('/')}{path}", json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def append_log(log_path: Path, message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_questions(base_url: str, questions: list[dict[str, Any]], answer_path: Path, timeout: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with answer_path.open("w", encoding="utf-8") as f:
        for i, q in enumerate(questions, start=1):
            start = time.perf_counter()
            try:
                payload = post_json(base_url, "/question-answer", {"question": q["question"]}, timeout=timeout)
                error = ""
            except Exception as e:
                payload = {}
                error = str(e)
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            row = {
                **q,
                "answer": payload.get("answer", ""),
                "route": payload.get("route", ""),
                "route_confidence": payload.get("route_confidence"),
                "query_ir": payload.get("query_ir", {}),
                "adjudication": payload.get("adjudication", {}),
                "context": payload.get("context", []),
                "context_raw": payload.get("context_raw", []),
                "answer_file": payload.get("answer_file", ""),
                "elapsed_ms": payload.get("elapsed_ms") or elapsed_ms,
                "error": error or str(payload.get("error", "")),
            }
            rows.append(row)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            if i % 25 == 0 or i == len(questions):
                print(f"进度：{i}/{len(questions)}", flush=True)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Run scenario QA ablation experiment and write paper-ready results.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/api/v1")
    parser.add_argument("--csv", required=True)
    parser.add_argument("--questions", required=True)
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--rebuild-graph", action="store_true")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    model_id = str(config["model_id"])
    model_name = str(config["model_name"])
    removed_module = str(config["removed_module"])
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "运行日志.log"
    log_path.write_text("", encoding="utf-8")

    generated_at = datetime.now().replace(microsecond=0).isoformat()
    start_all = time.perf_counter()
    append_log(log_path, f"加载模型：{model_name}，去除模块：{removed_module}")
    append_log(log_path, "初始化当前 FMEA 模型。")
    post_json(args.base_url, "/set-top_k", {"top_k": args.top_k}, timeout=60)
    if args.rebuild_graph:
        append_log(log_path, f"当前模型清空并重建图谱：{args.csv}")
        post_json(args.base_url, "/clear-fmea-graph", {"confirm": True}, timeout=1800)
        post_json(args.base_url, "/create-fmea-graph", {"path": args.csv}, timeout=3600)

    questions = load_jsonl(Path(args.questions))
    answer_rows = run_questions(args.base_url, questions, output_dir / "模型回答.jsonl", args.timeout)
    append_log(log_path, f"完成请求：{len(answer_rows)}/{len(questions)}")

    detail_rows: list[dict[str, Any]] = []
    route_counts: Counter[str] = Counter()
    for seq, (q, payload) in enumerate(zip(questions, answer_rows), start=1):
        scored = score_answer(q, payload)
        answer = scored["answer"]
        route = route_label(payload, answer)
        route_counts[route] += 1
        adjudication = payload.get("adjudication") or {}
        adjudication_status = str(adjudication.get("status") or "none")
        should_reject = q.get("should_reject")
        rejected = adjudication_status in {"rejected", "conflict"} or "证据不足" in answer or "拒绝" in answer
        rejection_correct = int(rejected == bool(should_reject)) if should_reject is not None else None
        current_route_hit = route_hit(q, payload)
        current_slot_hit = slot_hit(q, payload)
        traceable = int(not scored["unsupported_codes"] and not scored["unsupported_numbers"])
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
            "context": payload.get("context", []),
            "context_raw": payload.get("context_raw", []),
            "query_ir": payload.get("query_ir", {}),
            "adjudication": payload.get("adjudication", {}),
            "route_hit": current_route_hit,
            "slot_hit": current_slot_hit,
            "adjudication_status": adjudication_status,
            "missing_slots": adjudication.get("missing_slots") or payload.get("missing_slots") or [],
            "rejection_correct": rejection_correct,
            "traceable": traceable,
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
            "路由命中": current_route_hit,
            "槽位命中": current_slot_hit,
            "裁决状态": adjudication_status,
            "缺失槽位": adjudication.get("missing_slots") or payload.get("missing_slots") or [],
            "拒答正确": rejection_correct,
            "可追溯": traceable,
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
    summary = {
        "消融模型": model_name,
        "模型编号": model_id,
        "去除模块": removed_module,
        "配置文件": args.config,
        "生成时间": generated_at,
        "运行耗时秒": round(time.perf_counter() - start_all, 2),
        "总体指标": total_summary,
        "回答路径分布": dict(route_counts),
        "按情景类别统计": [
            {"分类": g["分类"], **{k: v for k, v in g.items() if k not in {"分组维度", "分类"}}}
            for g in group_summary_rows(detail_rows)
            if g["分组维度"] == "情景类别"
        ],
        "按模块标签统计": [
            {"分类": g["分类"], **{k: v for k, v in g.items() if k not in {"分组维度", "分类"}}}
            for g in group_summary_rows(detail_rows)
            if g["分组维度"] == "模块标签"
        ],
        "按题型统计": [
            {"分类": g["分类"], **{k: v for k, v in g.items() if k not in {"分组维度", "分类"}}}
            for g in group_summary_rows(detail_rows)
            if g["分组维度"] == "题型"
        ],
        "按来源标签统计": [
            {"分类": g["分类"], **{k: v for k, v in g.items() if k not in {"分组维度", "分类"}}}
            for g in group_summary_rows(detail_rows)
            if g["分组维度"] == "来源标签"
        ],
        "按难度统计": [
            {"分类": g["分类"], **{k: v for k, v in g.items() if k not in {"分组维度", "分类"}}}
            for g in group_summary_rows(detail_rows)
            if g["分组维度"] == "难度"
        ],
    }

    groups = group_summary_rows(detail_rows)
    write_jsonl(output_dir / "逐题明细.jsonl", detail_rows)
    csv_rows = []
    for row in detail_rows:
        csv_row = row.copy()
        for key in ("缺失文本项", "缺失数值项", "命中数值", "无证据编号", "无证据数值", "标准文本项", "标准数值项", "预期字段", "缺失槽位"):
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
        args.top_k,
        args.rebuild_graph,
        total_summary,
        groups,
        route_counts,
        [r for r in detail_rows if not r["correct"]],
    )
    append_log(
        log_path,
        f"完成：完全准确率={total_summary['完全准确率']}，平均部分准确率={total_summary['平均部分准确率']}",
    )
    print(json.dumps(summary["总体指标"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
