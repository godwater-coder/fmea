# -*- coding: utf-8 -*-

# 该文件承载控制策略偏好与控制覆盖存在性统计（预防/探测）相关问答分支。

import pandas as pd
import re


class DeterministicControlsPresenceMixin:
    def _try_answer_control_preference_by_project(self, question: str) -> dict | None:
        """确定性回答：给定引号中的项目，判断更偏向预防还是探测控制。"""

        q = (question or "").strip()
        if not q:
            return None
        if "主要依赖" not in q or "控制手段" not in q:
            return None
        if "预防" not in q or "探测" not in q:
            return None

        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        proj = str(kws[0]).strip()
        if not proj:
            return None

        rows = self._query_params(
            """
            MATCH (ps:ProcessStep)
            WHERE ps.ProcessStep IS NOT NULL AND toString(ps.ProcessStep) CONTAINS $proj
            MATCH (ps)<-[:occursAtProcessStep]-(fd:FailureMode)
            WITH
              sum(CASE WHEN fd.PreventControl IS NOT NULL AND trim(toString(fd.PreventControl)) <> '' THEN 1 ELSE 0 END) AS cPrev,
              sum(CASE WHEN fd.DetectionMeasure IS NOT NULL AND trim(toString(fd.DetectionMeasure)) <> '' THEN 1 ELSE 0 END) AS cDet,
              count(fd) AS total
            RETURN cPrev, cDet, total
            """.strip(),
            {"proj": proj},
        )
        if not rows:
            return None

        c_prev = int(rows[0].get("cPrev", 0) or 0)
        c_det = int(rows[0].get("cDet", 0) or 0)
        total = int(rows[0].get("total", 0) or 0)
        if total <= 0:
            return None

        used_csv_fallback = False
        if c_prev == 0 and c_det == 0:
            schema_rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.PreventControl IS NOT NULL
                   OR fd.DetectionMeasure IS NOT NULL
                   OR fd.TempMeasure IS NOT NULL
                RETURN count(fd) AS c
                """.strip(),
                {},
            )
            has_mode_controls = bool(schema_rows) and int(schema_rows[0].get("c", 0) or 0) > 0
            if not has_mode_controls:
                df = self._get_default_dfmea_df()
                if df is not None and {"ProcessStep", "FailureMode"}.issubset(set(df.columns)):
                    m = df["ProcessStep"].astype(str).str.contains(proj, na=False)
                    sub = df.loc[m].copy()
                    sub = sub[sub["FailureMode"].notna()]
                    total2 = int(sub.shape[0])
                    if total2 > 0:
                        used_csv_fallback = True
                        total = total2
                        if "PreventControl" in sub.columns:
                            c_prev = int((sub["PreventControl"].fillna("").astype(str).str.strip() != "").sum())
                        if "DetectionMeasure" in sub.columns:
                            c_det = int((sub["DetectionMeasure"].fillna("").astype(str).str.strip() != "").sum())

        if c_prev > c_det:
            pref = "预防"
        elif c_det > c_prev:
            pref = "探测"
        else:
            pref = "预防与探测并重"

        if c_prev == 0 and c_det == 0:
            pref = "（预防/探测字段均未记录）"
        answer = f"从文档记录看，“{proj}”相关失效模式更偏向依赖：{pref}（预防={c_prev}，探测={c_det}，总失效模式={total}）。"
        return {
            "answer": answer,
            "context": ["scope=project", f"project_kw={proj}", "control=prefer", f"csv_fallback={str(used_csv_fallback).lower()}"],
            "context_raw": {"prevent": c_prev, "detect": c_det, "total": total},
        }

    def _try_answer_modes_by_control_presence(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "失效模式" not in q or "预防" not in q or "探测" not in q:
            return None

        # 只统计失效模式主节点上的标准控制字段，避免跨节点推断造成失真。
        schema_rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.PreventControl IS NOT NULL
               OR fd.DetectionMeasure IS NOT NULL
               OR fd.TempMeasure IS NOT NULL
            RETURN count(fd) AS c
            """.strip(),
            {},
        )
        has_mode_controls = bool(schema_rows) and int(schema_rows[0].get("c", 0) or 0) > 0

        def _rows_to_items(rows: list[dict]) -> list[str]:
            items = [str(r.get("FailureMode") or "").strip() for r in rows]
            return [x for x in items if x]

        def _legacy_message(tag: str) -> dict:
            return {
                "answer": "当前知识图谱未写入失效模式级别的预防/探测字段，无法可靠统计（建议清空后重新导入 CSV 建图）。",
                "context": ["scope=global", f"controls={tag}", "legacy_graph_no_mode_controls=true"],
                "context_raw": {"modes": []},
            }

        # 同时具备预防与探测
        if "同时" in q and ("配备" in q or "具备" in q):
            if not has_mode_controls:
                df = self._get_default_dfmea_df()
                if df is None or "FailureMode" not in df.columns:
                    return _legacy_message("both")
                pc = df["PreventControl"].fillna("").astype(str).str.strip() if "PreventControl" in df.columns else pd.Series([""] * len(df))
                dc = df["DetectionMeasure"].fillna("").astype(str).str.strip() if "DetectionMeasure" in df.columns else pd.Series([""] * len(df))
                m = (pc != "") & (dc != "")
                items = sorted({str(x).strip() for x in df.loc[m, "FailureMode"].tolist() if str(x).strip() and str(x).lower() != "nan"})
                if not items:
                    return _legacy_message("both")
                answer = "同时配备预防性与探测性控制的失效模式包括：" + "，".join(items)
                return {
                    "answer": answer,
                    "context": ["scope=global", "controls=both", "list=modes", "csv_fallback=true"],
                    "context_raw": items,
                }
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.PreventControl IS NOT NULL AND trim(toString(fd.PreventControl)) <> ''
                  AND fd.DetectionMeasure IS NOT NULL AND trim(toString(fd.DetectionMeasure)) <> ''
                RETURN DISTINCT fd.FailureMode AS FailureMode
                ORDER BY FailureMode
                """.strip(),
                {},
            )
            items = _rows_to_items(rows)
            if not items:
                return None
            answer = "同时配备预防性与探测性控制的失效模式包括：" + "，".join(items)
            return {"answer": answer, "context": ["scope=global", "controls=both", "list=modes"], "context_raw": items}

        # 仅预防
        if "只有预防" in q and "没有探测" in q:
            if not has_mode_controls:
                df = self._get_default_dfmea_df()
                if df is None or "FailureMode" not in df.columns:
                    return _legacy_message("prevent_only")
                pc = df["PreventControl"].fillna("").astype(str).str.strip() if "PreventControl" in df.columns else pd.Series([""] * len(df))
                dc = df["DetectionMeasure"].fillna("").astype(str).str.strip() if "DetectionMeasure" in df.columns else pd.Series([""] * len(df))
                m = (pc != "") & (dc == "")
                items = sorted({str(x).strip() for x in df.loc[m, "FailureMode"].tolist() if str(x).strip() and str(x).lower() != "nan"})
                if not items:
                    return _legacy_message("prevent_only")
                answer = "只有预防性控制、没有探测性控制的失效模式包括：" + "，".join(items)
                return {
                    "answer": answer,
                    "context": ["scope=global", "controls=prevent_only", "list=modes", "csv_fallback=true"],
                    "context_raw": items,
                }
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.PreventControl IS NOT NULL AND trim(toString(fd.PreventControl)) <> ''
                  AND (fd.DetectionMeasure IS NULL OR trim(toString(fd.DetectionMeasure)) = '')
                RETURN DISTINCT fd.FailureMode AS FailureMode
                ORDER BY FailureMode
                """.strip(),
                {},
            )
            items = _rows_to_items(rows)
            if not items:
                return None
            answer = "只有预防性控制、没有探测性控制的失效模式包括：" + "，".join(items)
            return {
                "answer": answer,
                "context": ["scope=global", "controls=prevent_only", "list=modes"],
                "context_raw": items,
            }

        # 仅探测
        if "只有探测" in q and "没有预防" in q:
            if not has_mode_controls:
                df = self._get_default_dfmea_df()
                if df is None or "FailureMode" not in df.columns:
                    return _legacy_message("detect_only")
                pc = df["PreventControl"].fillna("").astype(str).str.strip() if "PreventControl" in df.columns else pd.Series([""] * len(df))
                dc = df["DetectionMeasure"].fillna("").astype(str).str.strip() if "DetectionMeasure" in df.columns else pd.Series([""] * len(df))
                m = (dc != "") & (pc == "")
                items = sorted({str(x).strip() for x in df.loc[m, "FailureMode"].tolist() if str(x).strip() and str(x).lower() != "nan"})
                if not items:
                    return _legacy_message("detect_only")
                answer = "只有探测性控制、没有预防性控制的失效模式包括：" + "，".join(items)
                if "合理吗" in q:
                    answer += "。是否合理需要结合工况与成本权衡，但仅从表格信息看，缺少预防控制通常意味着更依赖检测发现问题。"
                return {
                    "answer": answer,
                    "context": ["scope=global", "controls=detect_only", "list=modes", "csv_fallback=true"],
                    "context_raw": items,
                }
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.DetectionMeasure IS NOT NULL AND trim(toString(fd.DetectionMeasure)) <> ''
                  AND (fd.PreventControl IS NULL OR trim(toString(fd.PreventControl)) = '')
                RETURN DISTINCT fd.FailureMode AS FailureMode
                ORDER BY FailureMode
                """.strip(),
                {},
            )
            items = _rows_to_items(rows)
            if not items:
                return None
            answer = "只有探测性控制、没有预防性控制的失效模式包括：" + "，".join(items)
            if "合理吗" in q:
                answer += "。是否合理需要结合工况与成本权衡，但仅从表格信息看，缺少预防控制通常意味着更依赖检测发现问题。"
            return {"answer": answer, "context": ["scope=global", "controls=detect_only", "list=modes"], "context_raw": items}

        return None

    def _try_answer_threats_by_protection_level(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "提高防护等级" not in q:
            return None
        if "外部威胁" not in q:
            return None

        rows_modes = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.PreventControl IS NOT NULL
              AND trim(toString(fd.PreventControl)) <> ''
              AND (toString(fd.PreventControl) CONTAINS '提高防护等级' OR toString(fd.PreventControl) CONTAINS '防护等级')
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY FailureMode
            """.strip(),
            {},
        )
        modes = [str(r.get("FailureMode") or "").strip() for r in rows_modes]
        modes = [m for m in modes if m]
        if not modes:
            return None

        threats: list[str] = []
        blob = " ".join(modes)
        if "灰尘" in blob or "粉尘" in blob or "进灰" in blob or "尘" in blob:
            threats.append("灰尘/粉尘")
        if "进水" in blob or "水" in blob:
            threats.append("进水/水侵")
        if "潮" in blob or "湿" in blob:
            threats.append("潮湿/凝露")

        if not threats:
            # 回退：直接取最具代表性的失效模式描述
            threats = modes[:4]

        answer = "提高防护等级（如 IP 等级）主要用于抵御外部威胁：" + "，".join(threats) + "。"
        return {
            "answer": answer,
            "context": ["scope=global", "prevent_kw=提高防护等级", "list=threats"],
            "context_raw": {"threats": threats, "modes": modes},
        }
