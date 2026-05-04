# -*- coding: utf-8 -*-

# 该文件承载控制措施相关的实体映射查询（控制词->失效模式/项目、失效模式->控制项）。

import re
from synonyms import INTENT_SYNONYMS


class DeterministicControlsLookupMixin:
    def _try_answer_modes_by_control_keyword(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None

        # 探测控制 -> 失效模式
        if any(p in q for p in INTENT_SYNONYMS.get("detect_use", [])) and "失效模式" in q:
            # 优先使用新图结构：DetectionMeasure 直接挂在 FailureMode 上
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.DetectionMeasure IS NOT NULL
                  AND trim(toString(fd.DetectionMeasure)) <> ''
                  AND toString(fd.DetectionMeasure) CONTAINS $kw
                RETURN DISTINCT fd.FailureMode AS FailureMode
                ORDER BY FailureMode
                """.strip(),
                {"kw": kw},
            )
            # 回退兼容：旧图把措施信息存放在 FailureMeasure 节点
            if not rows:
                rows = self._query_params(
                    """
                    MATCH (fd:FailureMode)-[:isDueToFailureCause]->(:FailureCause)-[:isImprovedByFailureMeasure]->(fm:FailureMeasure)
                    WHERE (fm.DetectionMeasure IS NOT NULL AND toString(fm.DetectionMeasure) CONTAINS $kw)
                       OR (fm.FailureMeasure IS NOT NULL AND toString(fm.FailureMeasure) CONTAINS $kw)
                    RETURN DISTINCT fd.FailureMode AS FailureMode
                    ORDER BY FailureMode
                    """.strip(),
                    {"kw": kw},
                )
            items = [str(r.get("FailureMode") or "").strip() for r in rows]
            items = [x for x in items if x]
            if not items:
                return None
            answer = f"探测性控制“{kw}”用于探测的失效模式包括：" + "，".join(items)
            return {
                "answer": answer,
                "context": ["scope=global", f"ctrl={kw}", "list=modes"],
                "context_raw": items,
            }

        # 控制措施 -> 设计项目
        if "主要应用于哪些设计项目" in q:
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
                WHERE (
                    (fd.DetectionMeasure IS NOT NULL AND trim(toString(fd.DetectionMeasure)) <> '' AND toString(fd.DetectionMeasure) CONTAINS $kw)
                 OR (fd.PreventControl IS NOT NULL AND trim(toString(fd.PreventControl)) <> '' AND toString(fd.PreventControl) CONTAINS $kw)
                 OR (fd.TempMeasure IS NOT NULL AND trim(toString(fd.TempMeasure)) <> '' AND toString(fd.TempMeasure) CONTAINS $kw)
                )
                RETURN DISTINCT ps.ProcessStep AS ProcessStep
                ORDER BY ProcessStep
                """.strip(),
                {"kw": kw},
            )
            if not rows:
                rows = self._query_params(
                    """
                    MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
                    OPTIONAL MATCH (fd)-[:isDueToFailureCause]->(:FailureCause)-[:isImprovedByFailureMeasure]->(fm:FailureMeasure)
                    WHERE (fm.DetectionMeasure IS NOT NULL AND toString(fm.DetectionMeasure) CONTAINS $kw)
                       OR (fm.FailureMeasure IS NOT NULL AND toString(fm.FailureMeasure) CONTAINS $kw)
                    RETURN DISTINCT ps.ProcessStep AS ProcessStep
                    ORDER BY ProcessStep
                    """.strip(),
                    {"kw": kw},
                )
            items = [str(r.get("ProcessStep") or "").strip() for r in rows]
            items = [x for x in items if x]
            if not items:
                return None
            answer = f"“{kw}”主要应用于这些设计项目：" + "，".join(items)
            return {
                "answer": answer,
                "context": ["scope=global", f"ctrl={kw}", "list=projects"],
                "context_raw": items,
            }

        # 预防控制 -> 失效模式
        if "这一预防措施" in q and "主要防止哪些失效" in q:
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.PreventControl IS NOT NULL
                  AND trim(toString(fd.PreventControl)) <> ''
                  AND toString(fd.PreventControl) CONTAINS $kw
                RETURN DISTINCT fd.FailureMode AS FailureMode
                ORDER BY FailureMode
                """.strip(),
                {"kw": kw},
            )
            if not rows:
                rows = self._query_params(
                    """
                    MATCH (fd:FailureMode)-[:isDueToFailureCause]->(:FailureCause)-[:isImprovedByFailureMeasure]->(fm:FailureMeasure)
                    WHERE fm.FailureMeasure IS NOT NULL AND toString(fm.FailureMeasure) CONTAINS $kw
                    RETURN DISTINCT fd.FailureMode AS FailureMode
                    ORDER BY FailureMode
                    """.strip(),
                    {"kw": kw},
                )
            items = [str(r.get("FailureMode") or "").strip() for r in rows]
            items = [x for x in items if x]
            if not items:
                return None
            answer = f"预防性控制“{kw}”主要涉及/预防的失效模式包括：" + "，".join(items)
            return {
                "answer": answer,
                "context": ["scope=global", f"prevent_kw={kw}", "list=modes"],
                "context_raw": items,
            }

        return None

    def _try_answer_control_category_by_keyword(self, question: str) -> dict | None:
        """确定性回答：判断“X”属于预防、探测还是临时措施。"""

        q = (question or "").strip()
        if not q:
            return None
        if "是预防措施还是探测措施" not in q:
            return None
        if "临时措施" not in q:
            return None

        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            RETURN
              sum(CASE WHEN fd.PreventControl IS NOT NULL AND trim(toString(fd.PreventControl)) <> '' AND toString(fd.PreventControl) CONTAINS $kw THEN 1 ELSE 0 END) AS cPrev,
              sum(CASE WHEN fd.DetectionMeasure IS NOT NULL AND trim(toString(fd.DetectionMeasure)) <> '' AND toString(fd.DetectionMeasure) CONTAINS $kw THEN 1 ELSE 0 END) AS cDet,
              sum(CASE WHEN fd.TempMeasure IS NOT NULL AND trim(toString(fd.TempMeasure)) <> '' AND toString(fd.TempMeasure) CONTAINS $kw THEN 1 ELSE 0 END) AS cTemp
            """.strip(),
            {"kw": kw},
        )
        c_prev = int(rows[0].get("cPrev", 0) or 0) if rows else 0
        c_det = int(rows[0].get("cDet", 0) or 0) if rows else 0
        c_temp = int(rows[0].get("cTemp", 0) or 0) if rows else 0

        # 若专用字段未命中，回退兼容旧图结构
        if c_prev == 0 and c_det == 0 and c_temp == 0:
            rows2 = self._query_params(
                """
                MATCH (fm:FailureMeasure)
                WHERE (fm.DetectionMeasure IS NOT NULL AND trim(toString(fm.DetectionMeasure)) <> '' AND toString(fm.DetectionMeasure) CONTAINS $kw)
                   OR (fm.FailureMeasure IS NOT NULL AND trim(toString(fm.FailureMeasure)) <> '' AND toString(fm.FailureMeasure) CONTAINS $kw)
                RETURN DISTINCT toString(fm.FailureMeasure) AS FailureMeasure,
                                toString(fm.DetectionMeasure) AS DetectionMeasure
                LIMIT 200
                """.strip(),
                {"kw": kw},
            )

            has_det = False
            has_prev = False
            has_temp = False

            for r in rows2:
                det = str(r.get("DetectionMeasure") or "").strip()
                if det and det.lower() != "nan" and kw in det:
                    has_det = True

                blob = str(r.get("FailureMeasure") or "").strip()
                if not blob:
                    continue
                m_prev = re.search(r"预防控制：([^；]+)", blob)
                if m_prev and kw in m_prev.group(1):
                    has_prev = True
                m_temp = re.search(r"临时/改进措施：(.+)$", blob)
                if m_temp and kw in m_temp.group(1):
                    has_temp = True
                # 兼容历史遗留标签
                if "临时措施：" in blob and kw in blob:
                    has_temp = True
                if "探测控制：" in blob and kw in blob:
                    has_det = True

            labels: list[str] = []
            if has_prev:
                labels.append("预防措施")
            if has_det:
                labels.append("探测措施")
            if has_temp:
                labels.append("临时措施")
            if not labels:
                return None
            if len(labels) == 1:
                answer = f"“{kw}”在文档中属于{labels[0]}。"
            else:
                answer = f"“{kw}”在文档中同时出现在：" + "、".join(labels) + "。"
            return {
                "answer": answer,
                "context": ["scope=global", f"kw={kw}", "legacy_graph"],
                "context_raw": {"prevent": has_prev, "detect": has_det, "temp": has_temp},
            }

        labels: list[str] = []
        if c_prev > 0:
            labels.append("预防措施")
        if c_det > 0:
            labels.append("探测措施")
        if c_temp > 0:
            labels.append("临时措施")

        if not labels:
            return None

        if len(labels) == 1:
            answer = f"“{kw}”在文档中属于{labels[0]}。"
        else:
            answer = f"“{kw}”在文档中同时出现在：" + "、".join(labels) + "。"

        return {
            "answer": answer,
            "context": ["scope=global", f"kw={kw}", f"cPrev={c_prev}", f"cDet={c_det}", f"cTemp={c_temp}"],
            "context_raw": {"cPrev": c_prev, "cDet": c_det, "cTemp": c_temp},
        }

    def _try_answer_controls_by_failure_mode(self, question: str) -> dict | None:
        """确定性回答：给定（引号内）失效模式，返回其预防/探测控制。"""

        q = (question or "").strip()
        if not q:
            return None

        is_detect = "探测性控制" in q or "探测性设计控制" in q
        is_prevent = "预防性" in q and "设计控制" in q
        if not (is_detect or is_prevent):
            return None
        if "现行" not in q or "是什么" not in q:
            return None

        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None

        # 先确认失效模式存在，避免用户引号文本与失效模式无关时误匹配。
        rows_modes = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.FailureMode IS NOT NULL AND toString(fd.FailureMode) CONTAINS $kw
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY FailureMode
            LIMIT 5
            """.strip(),
            {"kw": kw},
        )
        matched_modes = [str(r.get("FailureMode") or "").strip() for r in rows_modes]
        matched_modes = [x for x in matched_modes if x]
        if not matched_modes:
            return None

        mode_label = matched_modes[0] if len(matched_modes) == 1 else kw

        if is_detect:
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.FailureMode IS NOT NULL AND toString(fd.FailureMode) CONTAINS $kw
                RETURN DISTINCT toString(fd.DetectionMeasure) AS v
                """.strip(),
                {"kw": kw},
            )
            items = [str(r.get("v") or "").strip() for r in rows]
            items = [x for x in items if x and x.lower() != "nan"]
            if not items:
                # 注意：这里不要回退到旧图链路（FailureCause->FailureMeasure）。
                # 因为措施挂在原因上且可能被多个模式共享，会造成跨模式污染。
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

                # 旧图安全回退：从默认 dfmea_final.csv 读取行级真值。
                used_csv_fallback = False
                if not has_mode_controls:
                    df = self._get_default_dfmea_df()
                    if df is not None and {"FailureMode", "DetectionMeasure"}.issubset(set(df.columns)):
                        m = df["FailureMode"].astype(str).str.contains(kw, na=False)
                        vals = df.loc[m, "DetectionMeasure"].fillna("").astype(str).str.strip().tolist()
                        vals = [v for v in vals if v and v.lower() != "nan"]
                        if vals:
                            used_csv_fallback = True
                            items = vals

                if items:
                    answer = f"针对“{mode_label}”，现行探测性设计控制包括：" + "，".join(sorted(set(items))) + "。"
                    return {
                        "answer": answer,
                        "context": [
                            "scope=global",
                            f"mode_kw={kw}",
                            "control=detect",
                            f"csv_fallback={str(used_csv_fallback).lower()}",
                        ],
                        "context_raw": items,
                    }
                answer = f"针对“{mode_label}”，文档中未记录现行探测性设计控制。"
                return {
                    "answer": answer,
                    "context": [
                        "scope=global",
                        f"mode_kw={kw}",
                        "control=detect",
                        "controls=none",
                        f"legacy_graph_no_mode_controls={str(not has_mode_controls).lower()}",
                        "csv_fallback=false",
                    ],
                    "context_raw": {"matched_modes": matched_modes, "controls": []},
                }

            answer = f"针对“{mode_label}”，现行探测性设计控制包括：" + "，".join(sorted(set(items))) + "。"
            return {
                "answer": answer,
                "context": ["scope=global", f"mode_kw={kw}", "control=detect"],
                "context_raw": items,
            }

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.FailureMode IS NOT NULL AND toString(fd.FailureMode) CONTAINS $kw
            RETURN DISTINCT toString(fd.PreventControl) AS v
            """.strip(),
            {"kw": kw},
        )
        items = [str(r.get("v") or "").strip() for r in rows]
        items = [x for x in items if x and x.lower() != "nan"]
        if not items:
            # 同上，不使用 FailureCause->FailureMeasure 推导模式级控制。
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

            used_csv_fallback = False
            if not has_mode_controls:
                df = self._get_default_dfmea_df()
                if df is not None and {"FailureMode", "PreventControl"}.issubset(set(df.columns)):
                    m = df["FailureMode"].astype(str).str.contains(kw, na=False)
                    vals = df.loc[m, "PreventControl"].fillna("").astype(str).str.strip().tolist()
                    vals = [v for v in vals if v and v.lower() != "nan"]
                    if vals:
                        used_csv_fallback = True
                        items = vals

            if items:
                answer = f"针对“{mode_label}”，现行预防性设计控制包括：" + "，".join(sorted(set(items))) + "。"
                return {
                    "answer": answer,
                    "context": [
                        "scope=global",
                        f"mode_kw={kw}",
                        "control=prevent",
                        f"csv_fallback={str(used_csv_fallback).lower()}",
                    ],
                    "context_raw": items,
                }
            answer = f"针对“{mode_label}”，文档中未记录现行预防性设计控制。"
            return {
                "answer": answer,
                "context": [
                    "scope=global",
                    f"mode_kw={kw}",
                    "control=prevent",
                    "controls=none",
                    f"legacy_graph_no_mode_controls={str(not has_mode_controls).lower()}",
                    "csv_fallback=false",
                ],
                "context_raw": {"matched_modes": matched_modes, "controls": []},
            }

        answer = f"针对“{mode_label}”，现行预防性设计控制包括：" + "，".join(sorted(set(items))) + "。"
        return {
            "answer": answer,
            "context": ["scope=global", f"mode_kw={kw}", "control=prevent"],
            "context_raw": items,
        }

