# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


QUOTE_RE = re.compile(r"[“\"‘']([^”\"’']+)[”\"’']")
CODE_RE = re.compile(r"\b[A-Z]{1,8}(?:[-_]?[A-Z0-9]+)*\d+[A-Z0-9_-]*\b", re.I)


def infer_intent(kind: str) -> str:
    k = kind.lower()
    if "bool" in k or "verify" in k or "presence" in k:
        return "boolean_verification"
    if "avg" in k or "mean" in k or "count" in k or "stat" in k:
        return "aggregate_metric"
    if any(x in k for x in ("top", "max", "min", "extreme", "highest", "lowest")):
        return "extreme_metric"
    if any(x in k for x in ("list", "modes_by", "projects_by")):
        return "list_entities"
    if any(x in k for x in ("rpn", "sod", "risk_profile", "metric")):
        return "lookup_metric"
    if any(x in k for x in ("cause", "effect", "action", "control", "relation")):
        return "lookup_relation"
    return "semantic_search"


def infer_metric(row: dict[str, Any]) -> str:
    fields = {str(x).upper() for x in (row.get("expected_fields") or [])}
    question = str(row.get("question") or "").upper()
    for metric in ("RPN", "S", "O", "D"):
        if metric in fields or re.search(rf"(?<![A-Z]){metric}(?![A-Z])", question):
            return metric
    if any("控制" in x or "CONTROL" in x for x in fields):
        return "controls"
    return ""


def infer_route(row: dict[str, Any]) -> str:
    module = str(row.get("module_eval_target") or row.get("module_label") or "").upper()
    if module == "M1":
        return "csv_basic"
    if module == "M2":
        return "deterministic_rule"
    if module in {"M3", "M3B"}:
        return "semantic_rag"
    kind = str(row.get("kind") or "").lower()
    if any(x in kind for x in ("avg", "top", "max", "min", "count", "threshold")):
        return "deterministic_rule"
    return ""


def annotate(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    kind = str(out.get("kind") or out.get("题型") or "")
    values = QUOTE_RE.findall(str(out.get("question") or ""))
    values.extend(x for x in CODE_RE.findall(str(out.get("question") or "")) if x not in values)
    out["expected_intent"] = out.get("expected_intent") or infer_intent(kind)
    out["expected_entities"] = out.get("expected_entities") or [
        {"kind": "explicit", "value": value} for value in dict.fromkeys(v.strip() for v in values if v.strip())
    ]
    out["expected_metric"] = out.get("expected_metric") or infer_metric(out)
    out["expected_constraints"] = out.get("expected_constraints") or []
    out["expected_route"] = out.get("expected_route") or infer_route(out)
    out["should_reject"] = bool(out.get("should_reject", False))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Add gold QueryIR and routing fields to experiment JSONL files.")
    parser.add_argument("paths", nargs="+")
    args = parser.parse_args()
    for raw in args.paths:
        path = Path(raw)
        rows = [annotate(json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        print(json.dumps({"path": str(path), "rows": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
