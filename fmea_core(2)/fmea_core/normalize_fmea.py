# -*- coding: utf-8 -*-

"""将标准 FMEA 分析表或兼容表格转换为统一 FMEA 核心范式。

输入：CSV/Excel 文件
输出：统一范式的 JSON/CSV 记录
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "specs" / "fmea_core_schema.json"
MAPPING_PATH = ROOT / "specs" / "field_mapping_rules.yaml"
NORMALIZATION_PATH = ROOT / "specs" / "normalization_rules.yaml"


def _load_schema() -> dict[str, Any]:
    with SCHEMA_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"\s+", " ", text)
    text = text.replace("（", "(").replace("）", ")")
    text = text.replace("；", ";").replace("，", ",")
    return text


def _normalize_key(name: Any) -> str:
    if name is None:
        return ""
    key = str(name).strip()
    key = re.sub(r"\s+", " ", key)
    key = key.replace("（", "(").replace("）", ")")
    return key.lower()


def _normalize_value(value: Any, field_name: str) -> Any:
    if value is None:
        return None
    if field_name in {"severity", "occurrence", "detection", "rpn", "revised_severity", "revised_occurrence", "revised_detection", "revised_rpn"}:
        try:
            return float(str(value).strip())
        except Exception:
            return None
    if field_name in {"failure_mode", "failure_effect", "failure_cause", "prevention_control", "detection_control", "current_control", "recommended_action", "action_taken"}:
        text = _normalize_text(value)
        if text is None:
            return None
        parts = re.split(r"[;；|,，\n]+", text)
        cleaned = []
        for p in parts:
            s = p.strip()
            if not s:
                continue
            # remove numbered prefixes like '1、', '1.' or '1,' or '（1）'
            s = re.sub(r"^\s*[\(（]?\d+[\)）\.,、]?\s*", "", s)
            cleaned.append(s)
        return cleaned
    return _normalize_text(value)


def _build_alias_lookup(schema: dict[str, Any]) -> dict[str, str]:
    alias_lookup: dict[str, str] = {}
    for field_name, field_spec in schema.get("public_fields", {}).items():
        for alias in field_spec.get("aliases", []):
            alias_lookup[_normalize_key(alias)] = field_name
    return alias_lookup


def _collect_multi_effects(normalized_row_keys: dict[str, str], row: dict[str, Any]) -> list[str] | None:
    # combine multiple effect-like columns into failure_effect
    effect_keys = {
        "局部影响",
        "上层影响",
        "最终影响",
        "最终影响/结果",
        "过载失效",
        "损耗失效",
        "机械振动",
        "定义简述",
    }
    collected: list[str] = []
    normalized_effect_keys = {k.lower() for k in effect_keys}
    for raw_key, norm_key in normalized_row_keys.items():
        if norm_key in normalized_effect_keys:
            val = row.get(raw_key)
            if val is None:
                continue
            text = _normalize_text(val)
            if not text:
                continue
            parts = re.split(r"[;；|,，\n]+", text)
            for p in parts:
                s = p.strip()
                if not s:
                    continue
                s = re.sub(r"^\s*[\(（]?\d+[\)）\.,、]?\s*", "", s)
                collected.append(s)
    return collected if collected else None


def _combine_ext_fields_into_remarks(normalized: dict[str, Any]) -> None:
    if normalized.get("remarks") not in (None, [], ""):
        return
    ext_values: list[str] = []
    for key, value in normalized.items():
        if not key.startswith("ext_"):
            continue
        if value is None or value == []:
            continue
        if isinstance(value, list):
            for item in value:
                if item is None:
                    continue
                text = str(item).strip()
                if text:
                    ext_values.append(text)
        else:
            text = str(value).strip()
            if text:
                ext_values.append(text)
    if ext_values:
        deduped = list(dict.fromkeys(ext_values))
        normalized["remarks"] = "; ".join(deduped)


def _score_header_row(row_values: list[str | None], alias_lookup: dict[str, str]) -> tuple[int, int]:
    score = 0
    core_hits = 0
    core_fields = {"failure_mode", "failure_effect", "failure_cause", "severity", "occurrence", "detection_control", "current_control", "detection", "rpn", "recommended_action", "action_taken"}
    for value in row_values:
        if value is None:
            continue
        normalized_value = _normalize_key(value)
        if not normalized_value:
            continue
        if normalized_value in alias_lookup:
            field_name = alias_lookup[normalized_value]
            if field_name in core_fields:
                score += 3
                core_hits += 1
            else:
                score += 2
            continue
        for alias in alias_lookup:
            if alias in normalized_value or normalized_value in alias:
                score += 1
                break
    return score, core_hits


def _detect_header_row(raw_df: pd.DataFrame, schema: dict[str, Any]) -> tuple[int, list[str | None]]:
    alias_lookup = _build_alias_lookup(schema)
    for idx, row in raw_df.iterrows():
        values = [_normalize_text(cell) for cell in row.tolist()]
        if not any(values):
            continue
        score, core_hits = _score_header_row(values, alias_lookup)
        if score >= 4 and core_hits >= 1:
            return idx, values
    fallback_values = [_normalize_text(cell) for cell in raw_df.iloc[0].tolist()]
    return 0, fallback_values


def _find_data_start(raw_df: pd.DataFrame, header_idx: int) -> int:
    for row_idx in range(header_idx + 1, len(raw_df)):
        row_values = raw_df.iloc[row_idx].tolist()
        non_empty_count = sum(1 for cell in row_values if _normalize_text(cell) is not None)
        if non_empty_count >= 4:
            return row_idx
    return header_idx + 1


def _normalize_dataframe_rows(raw_df: pd.DataFrame, header_values: list[str | None], schema: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in raw_df.iterrows():
        row_dict: dict[str, Any] = {}
        for idx, header_value in enumerate(header_values):
            if idx >= len(row):
                break
            clean_header = _normalize_text(header_value) or f"column_{idx}"
            row_dict[clean_header] = row.iloc[idx]
        rows.append(normalize_row(row_dict, schema))
    return rows


def normalize_row(row: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    public_fields = schema.get("public_fields", {})
    normalized: dict[str, Any] = {field_name: None for field_name in public_fields.keys()}
    normalized_row_keys = {str(raw_key): _normalize_key(raw_key) for raw_key in row.keys()}

    matched_keys_by_field: dict[str, list[str]] = {}
    for raw_key, normalized_key in normalized_row_keys.items():
        if not normalized_key:
            continue
        for field_name, field_spec in public_fields.items():
            aliases = {_normalize_key(alias) for alias in field_spec.get("aliases", [])}
            if normalized_key in aliases:
                matched_keys_by_field.setdefault(field_name, []).append(raw_key)
                break

    for field_name, raw_keys in matched_keys_by_field.items():
        values: list[Any] = []
        for raw_key in raw_keys:
            value = _normalize_value(row[raw_key], field_name)
            if value is None:
                continue
            if isinstance(value, list):
                values.extend(value)
            else:
                values.append(value)
        if not values:
            continue
        multi_value = public_fields[field_name].get("multi_value", False)
        normalized[field_name] = values if multi_value else values[0]

    # 补齐常见的标准字段对应，若未命中则尝试按中文/英文名称自动匹配
    alias_map = {
        "fmea编号": "record_id",
        "产品": "item_process",
        "产品名称": "item_process",
        "设计项目": "item_process",
        "项目名称": "item_process",
        "系统名称": "item_process",
        "分析层级": "analysis_level",
        "项目/功能": "function",
        "功能描述": "function",
        "潜在失效模式": "failure_mode",
        "潜在失效后果": "failure_effect",
        "严酷度(s)": "severity",
        "严酷度等级s": "severity",
        "潜在失效原因/机理": "failure_cause",
        "失效机理": "failure_cause",
        "封装相关失效机理": "failure_cause",
        "芯片相关失效机理": "failure_cause",
        "失效原因1：器件本身缺陷": "failure_cause",
        "发生度(o)": "occurrence",
        "现行预防控制": "prevention_control",
        "现行探测控制": "detection_control",
        "可探测度(d)": "detection",
        "检测难度等级d": "detection",
        "风险优先数(rpn)": "rpn",
        "风险优先数rpn": "rpn",
        "措施优先级(ap)": "action_priority",
        "建议措施": "recommended_action",
        "改进措施": "recommended_action",
        "补充措施": "recommended_action",
        "控制措施": "prevention_control",
        "失效控制措施": "prevention_control",
        "失效控制": "prevention_control",
        "失效原因": "failure_cause",
        "失效原因1：器件本身缺陷": "failure_cause",
        "定义简述": "failure_effect",
        "过载失效": "failure_effect",
        "损耗失效": "failure_effect",
        "机械振动": "failure_effect",
        "备注": "remarks",
    }
    for normalized_key, target_field in alias_map.items():
        for raw_key, row_key in normalized_row_keys.items():
            if row_key == normalized_key and normalized.get(target_field) is None:
                normalized[target_field] = _normalize_value(row[raw_key], target_field)
                break

    # If multiple effect columns exist (局部影响/上层影响/最终影响), merge them
    try:
        multi_effects = _collect_multi_effects(normalized_row_keys, row)
        if multi_effects:
            existing_effect = normalized.get("failure_effect")
            if existing_effect is None:
                normalized["failure_effect"] = multi_effects
            else:
                if isinstance(existing_effect, list):
                    normalized["failure_effect"] = existing_effect + [x for x in multi_effects if x not in existing_effect]
                else:
                    normalized["failure_effect"] = [existing_effect] + [x for x in multi_effects if x != existing_effect]
    except Exception:
        pass

    # If rpn missing but S,O,D present, compute
    try:
        if normalized.get("rpn") is None:
            s = normalized.get("severity")
            o = normalized.get("occurrence")
            d = normalized.get("detection")
            if isinstance(s, (int, float)) and isinstance(o, (int, float)) and isinstance(d, (int, float)):
                normalized["rpn"] = float(s * o * d)
    except Exception:
        pass

    try:
        _combine_ext_fields_into_remarks(normalized)
    except Exception:
        pass

    return normalized


def _detect_delimiter(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8-sig") as fh:
            sample = fh.read(4096)
        for delimiter in [";", ",", "\t"]:
            if sample.count(delimiter) > 0:
                return delimiter
    except Exception:
        pass
    return ","


def normalize_table(file_path: str | Path) -> list[dict[str, Any]]:
    path = Path(file_path)
    schema = _load_schema()

    if path.suffix.lower() == ".csv":
        delimiter = _detect_delimiter(path)
        raw_df = pd.read_csv(path, encoding="utf-8-sig", sep=delimiter, header=None)
        header_idx, header_values = _detect_header_row(raw_df, schema)
        data_start = _find_data_start(raw_df, header_idx)
        data_rows = raw_df.iloc[data_start:]
        return _normalize_dataframe_rows(data_rows, header_values, schema)

    if path.suffix.lower() in {".xlsx", ".xls"}:
        # Maintain backwards compatibility: return combined rows from first detected sheet
        excel_file = pd.ExcelFile(path)
        all_sheets = {}
        for sheet_name in excel_file.sheet_names:
            raw_df = pd.read_excel(path, sheet_name=sheet_name, header=None)
            if raw_df.empty:
                continue
            header_idx, header_values = _detect_header_row(raw_df, schema)
            if header_idx is None:
                continue
            data_start = _find_data_start(raw_df, header_idx)
            data_rows = raw_df.iloc[data_start:]
            if data_rows.empty:
                continue
            rows = _normalize_dataframe_rows(data_rows, header_values, schema)
            all_sheets[sheet_name] = rows
        # if only one sheet detected, return its rows (backwards compatible)
        if len(all_sheets) == 1:
            return next(iter(all_sheets.values()))
        # otherwise return flattened rows across sheets
        flattened: list[dict[str, Any]] = []
        for v in all_sheets.values():
            flattened.extend(v)
        if flattened:
            return flattened
        raise ValueError("未检测到可识别的 FMEA 表头")

    raise ValueError("只支持 CSV/Excel 文件")


def save_as_json(records: list[dict[str, Any]], output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def save_as_csv(records: list[dict[str, Any]], output_path: str | Path) -> None:
    output_path = Path(output_path)
    df = pd.DataFrame(records)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")


def normalize_workbook(file_path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Normalize all detectable sheets in an Excel workbook and return a dict
    mapping sheet_name -> list of normalized records.
    """
    path = Path(file_path)
    if path.suffix.lower() not in {".xlsx", ".xls"}:
        raise ValueError("normalize_workbook only supports Excel files")
    schema = _load_schema()
    excel_file = pd.ExcelFile(path)
    results: dict[str, list[dict[str, Any]]] = {}
    for sheet_name in excel_file.sheet_names:
        raw_df = pd.read_excel(path, sheet_name=sheet_name, header=None)
        if raw_df.empty:
            continue
        header_idx, header_values = _detect_header_row(raw_df, schema)
        if header_idx is None:
            continue
        data_start = _find_data_start(raw_df, header_idx)
        data_rows = raw_df.iloc[data_start:]
        if data_rows.empty:
            continue
        rows = _normalize_dataframe_rows(data_rows, header_values, schema)
        # Post-process: if item_process missing, fill from sheet name; if failure_effect missing, use remarks
        for rec in rows:
            try:
                if not rec.get('item_process') and sheet_name:
                    rec['item_process'] = sheet_name
                if (not rec.get('failure_effect') or rec.get('failure_effect') in ([], None)) and rec.get('remarks'):
                    r = rec.get('remarks')
                    if isinstance(r, list):
                        rec['failure_effect'] = r
                    else:
                        text = _normalize_text(r)
                        if text:
                            rec['failure_effect'] = [text]
            except Exception:
                pass
        results[sheet_name] = rows
    return results


def generate_per_sheet_report(file_path: str | Path) -> dict[str, Any]:
    p = Path(file_path)
    workbook_results = normalize_workbook(p)
    schema = _load_schema()
    public_fields = list(schema.get('public_fields', {}).keys())
    report: dict[str, Any] = {}
    for sheet, rows in workbook_results.items():
        mapped_present = set()
        for r in rows:
            for f in public_fields:
                if r.get(f) not in (None, [], ''):
                    mapped_present.add(f)
        report[sheet] = {
            'rows': len(rows),
            'mapped_fields_present_in_data_count': len(mapped_present),
            'mapped_fields_present_in_data': sorted(list(mapped_present)),
        }
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="将 FMEA 表格转换为统一范式")
    parser.add_argument("input_file", help="输入 CSV/Excel 文件")
    parser.add_argument("--output", default="fmea_core/output/normalized_fmea.json", help="输出 JSON 文件")
    parser.add_argument("--format", choices=["json", "csv"], default="json", help="输出格式")
    args = parser.parse_args()

    records = normalize_table(args.input_file)
    if args.format == "json":
        save_as_json(records, args.output)
    else:
        save_as_csv(records, args.output)

    print(f"normalized_rows={len(records)}")
    print(f"output={args.output}")
