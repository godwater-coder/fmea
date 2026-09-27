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
PROJECT_SCHEMA_FIELDS = fmea_schema.PROJECT_SCHEMA_FIELDS
normalize_to_project_schema = fmea_schema.normalize_to_project_schema


DEFAULT_INPUT = Path("DATA/磷酸铁锂电池Dfmea分析/Dfmea案例.xls")
DEFAULT_OUTPUT = Path("data/磷酸铁锂电池FMECA分析表20250416105822.csv")
DEFAULT_REPORT = Path("DATA/磷酸铁锂电池Dfmea分析/标准化核查.json")


def _s(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    return str(value).strip()


def _find_header_row(raw: pd.DataFrame) -> int:
    for idx, row in raw.iterrows():
        values = {_s(v) for v in row.tolist()}
        if "潜在的失效模式" in values and ("设计项目" in values or "项目/功能" in values):
            return int(idx)
    raise ValueError("未找到 DFMEA 表头行：需要包含“设计项目”和“潜在的失效模式”。")


def read_lfp_dfmea_xls(path: Path, sheet_name: str = "dfmea") -> tuple[pd.DataFrame, int]:
    raw = pd.read_excel(path, sheet_name=sheet_name, header=None, engine="xlrd")
    header_idx = _find_header_row(raw)
    header = [_s(v) for v in raw.iloc[header_idx].tolist()]
    body = raw.iloc[header_idx + 1 :].copy()
    body.columns = header
    body = body.dropna(axis=1, how="all")
    body = body.dropna(how="all").reset_index(drop=True)
    body = body.loc[:, [bool(str(c).strip()) for c in body.columns]]
    return body, header_idx


def normalize_lfp_dfmea(input_path: Path, output_path: Path, sheet_name: str) -> dict[str, Any]:
    raw_df, header_idx = read_lfp_dfmea_xls(input_path, sheet_name=sheet_name)
    raw_df["FMEA编号"] = [f"LFP{i:03d}" for i in range(1, len(raw_df) + 1)]
    raw_df["产品"] = "磷酸铁锂电池"
    raw_df["分析层级"] = "DFMEA"

    normalized = normalize_to_project_schema(
        raw_df,
        source_file=str(input_path),
        dataset_id="lfp_battery_dfmea",
        project_id="lfp_battery_dfmea_case",
        domain="磷酸铁锂电池DFMEA",
        import_batch_id="lfp_dfmea_20250416105822",
    )
    normalized["SourceRowNo"] = [header_idx + 2 + i for i in range(len(normalized))]

    for field in PROJECT_SCHEMA_FIELDS:
        if field.name not in normalized.columns:
            normalized[field.name] = None
    ordered = [field.name for field in PROJECT_SCHEMA_FIELDS] + ["TempMeasure"]
    normalized = normalized.loc[:, [c for c in ordered if c in normalized.columns]]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized.to_csv(output_path, index=False, encoding="utf-8-sig")

    numeric_ranges: dict[str, dict[str, Any]] = {}
    for col in ("S", "O", "D", "RPN"):
        values = pd.to_numeric(normalized[col], errors="coerce") if col in normalized.columns else pd.Series(dtype=float)
        numeric_ranges[col] = {
            "min": None if values.dropna().empty else float(values.min()),
            "max": None if values.dropna().empty else float(values.max()),
            "nulls": int(values.isna().sum()),
        }

    report = {
        "input": str(input_path),
        "sheet": sheet_name,
        "output": str(output_path),
        "rows": int(len(normalized)),
        "columns": list(normalized.columns),
        "unique_fmea_ids": int(normalized["FmeaID"].nunique(dropna=True)),
        "missing_required": {
            "ProcessStep": int(normalized["ProcessStep"].isna().sum()),
            "FailureMode": int(normalized["FailureMode"].isna().sum()),
        },
        "numeric_ranges": numeric_ranges,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Standardize the LFP battery DFMEA xls into project-schema CSV.")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--sheet", default="dfmea")
    args = parser.parse_args()

    report = normalize_lfp_dfmea(Path(args.input), Path(args.output), args.sheet)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
