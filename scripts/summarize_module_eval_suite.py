# -*- coding: utf-8 -*-

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = ROOT / "实验/消融实验/zenodo_floating_wind_fmea/模块专项实验"
REQUIRED_FILES = [
    "模型回答.jsonl",
    "逐题明细.jsonl",
    "逐题明细.csv",
    "分类汇总.csv",
    "汇总指标.json",
    "使用题集.json",
    "实验报告.md",
    "运行日志.log",
]
MODULE_NAMES = {
    "M1": "M1_编号直答",
    "M2": "M2_规则推理",
    "M3": "M3_自然语言检索",
    "M4": "M4_证据裁决",
}
MODEL_ORDER = [
    "Baseline_legacy兼容模型",
    "Full_全量模型",
    "Full-R0_去除语义优先分流",
    "Full-M1_去除CSV直答模块",
    "Full-M2_去除确定性规则问答模块",
    "Full-M3_去除查询理解与检索增强模块",
    "Full-M3a_去除查询中间表示",
    "Full-M3b_去除语义检索增强",
    "Full-M4_去除证据检查与路由裁决模块",
    "Full-Route_固定顺序路由",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_model_rows(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = []
    module_rows = []
    for slug in MODEL_ORDER:
        result_dir = root / slug / "实验结果"
        summary_path = result_dir / "汇总指标.json"
        detail_path = result_dir / "逐题明细.jsonl"
        if not summary_path.exists() or not detail_path.exists():
            continue
        summary = load_json(summary_path)
        details = [json.loads(line) for line in detail_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        overall = summary.get("总体指标", {})
        rows.append(
            {
                "模型": summary.get("消融模型") or summary.get("模型") or slug,
                "模型编号": summary.get("模型编号", ""),
                "题数": overall.get("题数", overall.get("总题数", len(details))),
                "正确题数": overall.get("正确题数", 0),
                "完全准确率": overall.get("完全准确率", 0),
                "平均部分准确率": overall.get("平均部分准确率", 0),
                "平均耗时毫秒": overall.get("平均耗时毫秒", 0),
                "上下文精确率": overall.get("上下文精确率"),
                "证据召回率": overall.get("证据召回率"),
                "幻觉率": overall.get("幻觉率", 0),
                "多跳路径覆盖率": overall.get("多跳路径覆盖率"),
                "结果目录": str(result_dir.relative_to(ROOT)),
            }
        )
        for module, module_name in MODULE_NAMES.items():
            bucket = [r for r in details if r.get("module_eval_target") == module]
            if not bucket:
                continue
            module_rows.append(
                {
                    "模型": summary.get("消融模型") or summary.get("模型") or slug,
                    "模型编号": summary.get("模型编号", ""),
                    "模块": module,
                    "模块名称": module_name,
                    "题数": len(bucket),
                    "正确题数": sum(int(r.get("correct", 0)) for r in bucket),
                    "完全准确率": round(sum(int(r.get("correct", 0)) for r in bucket) / len(bucket), 4),
                    "平均部分准确率": round(sum(float(r.get("partial", 0)) for r in bucket) / len(bucket), 4),
                    "平均耗时毫秒": round(sum(float(r.get("elapsed_ms", 0)) for r in bucket) / len(bucket), 2),
                    "上下文精确率": _avg(bucket, "context_precision"),
                    "证据召回率": _avg(bucket, "evidence_recall"),
                    "幻觉率": _avg(bucket, "hallucination") or 0,
                    "多跳路径覆盖率": _avg(bucket, "multi_hop_path_coverage"),
                }
            )
    return rows, module_rows


def _avg(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [float(r[key]) for r in rows if r.get(key) is not None and str(r.get(key)) != ""]
    return round(sum(values) / len(values), 4) if values else None


def write_consistency_files(
    root: Path,
    question_path: str,
    total_questions: int,
    per_module: int,
) -> list[dict[str, Any]]:
    checks = []
    for slug in MODEL_ORDER:
        result_dir = root / slug / "实验结果"
        detail_path = result_dir / "逐题明细.jsonl"
        if not detail_path.exists():
            checks.append({"模型目录": slug, "状态": "未运行", "通过": False})
            continue
        details = [json.loads(line) for line in detail_path.read_text(encoding="utf-8").splitlines() if line.strip()] if detail_path.exists() else []
        module_counts = {m: sum(1 for r in details if r.get("module_eval_target") == m) for m in MODULE_NAMES}
        missing = [name for name in REQUIRED_FILES if not (result_dir / name).exists()]
        check = {
            "模型目录": slug,
            "题数": len(details),
            "模块专项题数": module_counts,
            "缺失文件": missing,
            "通过": len(details) == total_questions and all(v == per_module for v in module_counts.values()) and not missing,
        }
        write_json(result_dir / "一致性检查.json", check)
        (result_dir / "模块核查.md").write_text(
            "\n".join(
                [
                    f"# {slug} 模块专项实验核查",
                    "",
                    f"- 题集：`{question_path}`",
                    f"- 题数：{total_questions}",
                    f"- M1-M4：各{per_module}题",
                    f"- 实际分布：{module_counts}",
                    f"- 必需文件缺失：{missing or '无'}",
                    f"- 核查结果：{'通过' if check['通过'] else '未通过'}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        checks.append(check)
    write_json(root / "一致性检查.json", checks)
    return checks


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--questions", default="DATA/zenodo_floating_wind_fmea/module_eval/special_all_400_questions.jsonl")
    parser.add_argument("--per-module", type=int, default=100)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    overall_rows, module_rows = load_model_rows(root)
    total_questions = args.per_module * len(MODULE_NAMES)
    checks = write_consistency_files(root, args.questions, total_questions, args.per_module)

    overall_fields = [
        "模型", "模型编号", "题数", "正确题数", "完全准确率", "平均部分准确率",
        "平均耗时毫秒", "上下文精确率", "证据召回率", "幻觉率", "多跳路径覆盖率", "结果目录",
    ]
    module_fields = [
        "模型", "模型编号", "模块", "模块名称", "题数", "正确题数", "完全准确率",
        "平均部分准确率", "平均耗时毫秒", "上下文精确率", "证据召回率", "幻觉率", "多跳路径覆盖率",
    ]
    write_csv(root / "模块专项实验总汇总.csv", overall_rows, overall_fields)
    write_csv(root / "模块专项实验分模块汇总.csv", module_rows, module_fields)

    full = {r["模型"]: r for r in module_rows if r["模型"] == "Full全量模型"}
    comparison = []
    for row in module_rows:
        if row["模型"] in {"Full全量模型", "baseline模型"}:
            continue
        full_row = next((x for x in module_rows if x["模型"] == "Full全量模型" and x["模块"] == row["模块"]), None)
        if not full_row:
            continue
        comparison.append(
            {
                "模型": row["模型"],
                "模块": row["模块"],
                "Full准确率": full_row["完全准确率"],
                "消融后准确率": row["完全准确率"],
                "准确率变化": round(row["完全准确率"] - full_row["完全准确率"], 4),
                "Full平均耗时毫秒": full_row["平均耗时毫秒"],
                "消融后平均耗时毫秒": row["平均耗时毫秒"],
                "耗时变化毫秒": round(row["平均耗时毫秒"] - full_row["平均耗时毫秒"], 2),
            }
        )
    write_json(
        root / "模块专项实验总汇总.json",
        {
            "生成时间": datetime.now().replace(microsecond=0).isoformat(),
            "题集": args.questions,
            "专项题分布": {module: args.per_module for module in MODULE_NAMES},
            "总体指标": overall_rows,
            "分模块指标": module_rows,
            "Full与消融差值": comparison,
            "一致性检查": checks,
        },
    )

    lines = [
        "# 模块专项实验汇总",
        "",
        f"题集：`{args.questions}`，M1-M4 各{args.per_module}题。",
        "",
        "## 总体结果",
        "",
        "| 模型 | 题数 | 完全准确率 | 平均部分准确率 | 平均耗时(ms) | 上下文精确率 | 证据召回率 | 幻觉率 | 多跳路径覆盖率 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in overall_rows:
        lines.append(
            f"| {r['模型']} | {r['题数']} | {r['完全准确率']} | {r['平均部分准确率']} | "
            f"{r['平均耗时毫秒']} | {r['上下文精确率']} | {r['证据召回率']} | {r['幻觉率']} | {r['多跳路径覆盖率']} |"
        )
    lines.extend(["", "## 分模块完全准确率", ""])
    lines.append("| 模型 | M1 编号直答 | M2 规则推理 | M3 自然语言检索 | M4 证据裁决 |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for model in MODEL_ORDER:
        label = next(
            (
                r["模型"]
                for r in overall_rows
                if f"/{model}/实验结果" in f"/{str(r['结果目录']).replace(chr(92), '/')}"
            ),
            model,
        )
        values = []
        for module in ("M1", "M2", "M3", "M4"):
            row = next((r for r in module_rows if r["模型"] == label and r["模块"] == module), None)
            values.append(row["完全准确率"] if row else "")
        lines.append(f"| {label} | {' | '.join(str(x) for x in values)} |")
    lines.extend(["", "## 解释", "", "- `Full-Mi` 结果只表示移除一个模块后的同题性能，不等同于该模块独立贡献的严格因果估计。", "- 本目录的专项题用于检验模块是否在其目标问题上产生可观测影响；Baseline 使用 legacy 兼容 CSV。", ""])
    (root / "模块专项实验总报告.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"overall": overall_rows, "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
