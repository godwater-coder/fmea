# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import json
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "实验" / "最终实验汇总"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def summary_row(dataset: str, experiment: str, path: Path) -> dict[str, Any]:
    payload = load_json(path)
    metrics = payload.get("总体指标", {})
    return {
        "数据集": dataset,
        "实验": experiment,
        "题数": metrics.get("题数"),
        "完全准确率": metrics.get("完全准确率"),
        "平均部分准确率": metrics.get("平均部分准确率"),
        "平均耗时毫秒": metrics.get("平均耗时毫秒"),
        "上下文精确率": metrics.get("上下文精确率"),
        "证据召回率": metrics.get("证据召回率"),
        "幻觉率": metrics.get("幻觉率"),
        "多跳路径覆盖率": metrics.get("多跳路径覆盖率"),
        "路由命中率": metrics.get("路由命中率"),
        "槽位解析命中率": metrics.get("槽位解析命中率"),
        "可追溯率": metrics.get("可追溯率"),
        "拒答正确率": metrics.get("拒答正确率"),
        "裁决状态分布": metrics.get("裁决状态分布"),
        "结果文件": str(path.relative_to(ROOT)),
    }


def collect_main() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    roots = {
        "Zenodo": ROOT / "实验/消融实验/zenodo_floating_wind_fmea",
        "磷酸铁锂电池DFMEA": ROOT / "实验/消融实验/磷酸铁锂电池DFMEA",
    }
    for dataset, root in roots.items():
        for path in sorted(root.glob("*/实验结果/汇总指标.json")):
            rows.append(summary_row(dataset, path.parent.parent.name, path))
    baseline_paths = {
        "Zenodo": ROOT / "实验/对比实验/baseline/zenodo_floating_wind_fmea/实验结果/汇总指标.json",
    }
    for dataset, path in baseline_paths.items():
        if path.exists() and not any(r["数据集"] == dataset and "Baseline" in r["实验"] for r in rows):
            rows.append(summary_row(dataset, "Baseline", path))
    return rows


def collect_special() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    roots = {
        "Zenodo": ROOT / "实验/消融实验/zenodo_floating_wind_fmea/模块专项实验",
        "磷酸铁锂电池DFMEA": ROOT / "实验/消融实验/磷酸铁锂电池DFMEA/模块专项实验",
    }
    for dataset, root in roots.items():
        for path in sorted(root.glob("*/实验结果/汇总指标.json")):
            rows.append(summary_row(dataset, path.parent.parent.name, path))
    llm_roots = {
        "Zenodo": ROOT / "实验/对比实验/LLM/zenodo_floating_wind_fmea/模块专项",
        "磷酸铁锂电池DFMEA": ROOT / "实验/对比实验/LLM/磷酸铁锂电池DFMEA/模块专项",
    }
    for dataset, root in llm_roots.items():
        for path in sorted(root.glob("*/实验结果/汇总指标.json")):
            rows.append(summary_row(dataset, f"LLM-{path.parent.parent.name}", path))
    return rows


def repeat_stats() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for dataset, folder in (("Zenodo", "zenodo"), ("磷酸铁锂电池DFMEA", "lfp")):
        metrics: list[dict[str, Any]] = []
        for run in (1, 2, 3):
            path = ROOT / f"实验/重复实验/{folder}/run{run}/Full_全量模型/实验结果/汇总指标.json"
            metrics.append(load_json(path)["总体指标"])
        row: dict[str, Any] = {"数据集": dataset, "重复次数": 3}
        for key in ("完全准确率", "平均部分准确率", "平均耗时毫秒", "上下文精确率", "证据召回率", "幻觉率", "路由命中率", "槽位解析命中率"):
            values = [float(m[key]) for m in metrics if m.get(key) is not None]
            if values:
                row[f"{key}_均值"] = round(statistics.mean(values), 6)
                row[f"{key}_标准差"] = round(statistics.pstdev(values), 6)
        out.append(row)
    return out


def reverse_analysis() -> list[dict[str, Any]]:
    datasets = {
        "Zenodo": load_jsonl(ROOT / "实验/消融实验/zenodo_floating_wind_fmea/Full_全量模型/实验结果/逐题明细.jsonl"),
        "磷酸铁锂电池DFMEA": load_jsonl(ROOT / "实验/消融实验/磷酸铁锂电池DFMEA/Full_全量模型/实验结果/逐题明细.jsonl"),
    }
    # The first two reverse-query kinds belong to Zenodo; risk_colloquial is
    # defined only in the battery main set.  Keep the source explicit so an
    # absent kind cannot silently turn into a misleading 0/0 result.
    targets = (
        ("Zenodo", "mode_full_risk_profile"),
        ("Zenodo", "mode_effect_to_rpn"),
        ("磷酸铁锂电池DFMEA", "risk_colloquial"),
    )
    out: list[dict[str, Any]] = []
    for dataset, kind in targets:
        rows = datasets[dataset]
        bucket = [r for r in rows if str(r.get("kind") or "") == kind]
        wrong = [r for r in bucket if not int(r.get("correct") or 0)]
        causes: Counter[str] = Counter()
        for row in wrong:
            status = str(row.get("adjudication_status") or "")
            if row.get("route_hit") == 0:
                causes["路由错误"] += 1
            elif row.get("slot_hit") == 0:
                causes["解析/槽位错误"] += 1
            elif status in {"rejected", "conflict", "insufficient"}:
                causes["裁决误判"] += 1
            elif row.get("evidence_recall") is not None and float(row.get("evidence_recall") or 0) < 1:
                causes["召回不足"] += 1
            else:
                causes["答案生成或评分不匹配"] += 1
        out.append({
            "数据集": dataset,
            "题型": kind,
            "题数": len(bucket),
            "正确题数": len(bucket) - len(wrong),
            "准确率": round((len(bucket) - len(wrong)) / len(bucket), 4) if bucket else None,
            "错误原因": dict(causes),
            "结论": "写入局限并优先修复占比最高的错误原因" if wrong else "未观察到反效果",
        })
    return out


def completion_check(main: list[dict[str, Any]], special: list[dict[str, Any]]) -> dict[str, Any]:
    checks = {
        "Zenodo主实验实验臂数": sum(r["数据集"] == "Zenodo" for r in main),
        "电池主实验实验臂数": sum(r["数据集"] == "磷酸铁锂电池DFMEA" for r in main),
        "Zenodo专项实验臂数": sum(r["数据集"] == "Zenodo" for r in special),
        "电池专项实验臂数": sum(r["数据集"] == "磷酸铁锂电池DFMEA" for r in special),
        "重复实验结果数": len(list((ROOT / "实验/重复实验").glob("*/run*/Full_全量模型/实验结果/汇总指标.json"))),
        "题集槽位标注": {},
    }
    for path in (
        ROOT / "DATA/zenodo_floating_wind_fmea/module_eval/special_all_400_questions.jsonl",
        ROOT / "DATA/zenodo_floating_wind_fmea/scenario_qa_no_id/all_scenario_no_id_1500_questions.jsonl",
        ROOT / "DATA/磷酸铁锂电池Dfmea分析/eval/lfp_dfmea_500_questions.jsonl",
        ROOT / "DATA/磷酸铁锂电池Dfmea分析/module_eval/lfp_module_special_200_questions.jsonl",
    ):
        rows = load_jsonl(path)
        checks["题集槽位标注"][str(path.relative_to(ROOT))] = {
            "题数": len(rows),
            "含expected_intent": sum(bool(r.get("expected_intent")) for r in rows),
            "含expected_entities": sum(bool(r.get("expected_entities")) for r in rows),
            "含should_reject": sum(bool(r.get("should_reject")) for r in rows),
        }
    checks["通过"] = (
        checks["Zenodo主实验实验臂数"] >= 10
        and checks["电池主实验实验臂数"] >= 10
        and checks["Zenodo专项实验臂数"] >= 12
        and checks["电池专项实验臂数"] >= 12
        and checks["重复实验结果数"] == 6
    )
    return checks


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    main_rows = collect_main()
    special_rows = collect_special()
    repeats = repeat_stats()
    reverse = reverse_analysis()
    completion = completion_check(main_rows, special_rows)
    write_csv(OUT / "主实验汇总.csv", main_rows)
    write_csv(OUT / "专项实验汇总.csv", special_rows)
    write_csv(OUT / "三次重复稳健性.csv", repeats)
    write_csv(OUT / "反向题型归因.csv", reverse)
    write_json(OUT / "执行完成核查.json", completion)
    write_json(OUT / "全部实验汇总.json", {"生成时间": datetime.now().isoformat(timespec="seconds"), "主实验": main_rows, "专项实验": special_rows, "重复实验": repeats, "反向题型归因": reverse, "完成核查": completion})
    lines = ["# 最终实验汇总", "", f"生成时间：{datetime.now().isoformat(timespec='seconds')}", "", f"完成核查：{'通过' if completion['通过'] else '未通过'}", "", "## 三次重复", ""]
    for row in repeats:
        lines.append(f"- {row['数据集']}：准确率 {row.get('完全准确率_均值')} ± {row.get('完全准确率_标准差')}，耗时 {row.get('平均耗时毫秒_均值')} ± {row.get('平均耗时毫秒_标准差')} ms。")
    lines.extend(["", "## 反向题型归因", ""])
    for row in reverse:
        lines.append(f"- {row['题型']}：{row['正确题数']}/{row['题数']}，准确率={row['准确率']}，错误原因={row['错误原因']}。")
    lines.extend(["", "## 文件", "", "- `主实验汇总.csv`", "- `专项实验汇总.csv`", "- `三次重复稳健性.csv`", "- `反向题型归因.csv`", "- `执行完成核查.json`", "- `全部实验汇总.json`", ""])
    (OUT / "最终实验报告.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(completion, ensure_ascii=False, indent=2))
    return 0 if completion["通过"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
