# -*- coding: utf-8 -*-

# 该文件承载“按设计项目/工序”维度的规则化问答分支与指标提取工具。

import re
from synonyms import INTENT_SYNONYMS, METRIC_SYNONYMS


class DeterministicProcessStepMixin:
    def _try_answer_failure_modes_by_process_step(self, question: str) -> dict | None:
        """Deterministic answer for: '<设计项目/工序> 对应的潜在失效模式是什么'.

        Why: LLM 生成 Cypher 容易因为实体不精确（如“动力电池设计项目” vs 图中“动力电池”）
        而回退到向量检索/高温度回答，导致把其他工序的失效模式/失效原因混入答案。
        """
        ps_key = self._extract_process_step_from_question(question)
        if not ps_key:
            return None

        matched_name = self._match_process_step_name(ps_key)
        if not matched_name:
            return None

        # 2) 直接查该 ProcessStep 下所有 FailureMode
        modes = self._query_params(
            """
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {ProcessStep: $step})
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY fd.FailureMode
            """,
            {"step": matched_name},
        )
        items = [str(r.get("FailureMode") or "").strip() for r in modes]
        items = [x for x in items if x]

        # 支持“除了A外/不包括A”这类排除语义
        exclusion_terms = self._extract_exclusion_terms(question)
        if exclusion_terms:
            exclusion_keywords: list[str] = []
            for term in exclusion_terms:
                exclusion_keywords.extend(self._expand_exclusion_keywords(term))

            def _is_excluded(mode: str) -> bool:
                m = re.sub(r"\s+", "", str(mode or ""))
                for kw in exclusion_keywords:
                    if kw and kw in m:
                        return True
                return False

            items = [x for x in items if not _is_excluded(x)]

        if not items:
            if exclusion_terms:
                ex_txt = "，".join(exclusion_terms)
                return {
                    "answer": f"{matched_name} 除“{ex_txt}”外暂无其他潜在失效模式。",
                    "context": [f"ProcessStep={matched_name}", f"excluded={ex_txt}"],
                    "context_raw": [],
                }
            return None

        answer = f"{matched_name} 对应的潜在失效模式包括：" + "，".join(items)
        if exclusion_terms:
            ex_txt = "，".join(exclusion_terms)
            answer = f"{matched_name} 除“{ex_txt}”外的潜在失效模式包括：" + "，".join(items)
        return {
            "answer": answer,
            "context": [f"ProcessStep={matched_name}"] + ([f"excluded={ '，'.join(exclusion_terms)}"] if exclusion_terms else []),
            "context_raw": items,
        }

    def _match_process_step_name(self, ps_key: str) -> str | None:
        """Find the best matching ProcessStep name in graph."""
        ps_key = self._normalize_process_step_name(ps_key or "")
        if not ps_key:
            return None

        rows = self._query_params(
            "MATCH (ps:ProcessStep {ProcessStep: $name}) RETURN ps.ProcessStep AS name LIMIT 1",
            {"name": ps_key},
        )
        matched_name = rows[0].get("name") if rows else None
        if matched_name:
            return str(matched_name).strip() or None

        candidates = self._query_params(
            """
            WITH $key AS key
            MATCH (ps:ProcessStep)
            WHERE ps.ProcessStep CONTAINS key OR key CONTAINS ps.ProcessStep
            RETURN ps.ProcessStep AS name
            ORDER BY size(ps.ProcessStep) DESC
            LIMIT 10
            """,
            {"key": ps_key},
        )
        if candidates:
            return str(candidates[0].get("name") or "").strip() or None
        return None

    @staticmethod
    def _extract_avg_metric_from_question(question: str) -> str | None:
        q = (question or "").strip()
        if "平均" not in q:
            return None
        # 常见指标同义词（集中映射见 synonyms.py）
        s_rule = METRIC_SYNONYMS.get("S", {})
        o_rule = METRIC_SYNONYMS.get("O", {})
        d_rule = METRIC_SYNONYMS.get("D", {})

        if any(k in q for k in (s_rule.get("keywords") or [])) or re.search(
            str(s_rule.get("regex") or ""), q, re.IGNORECASE
        ):
            return "S"
        if any(k in q for k in (o_rule.get("keywords") or [])) or re.search(
            str(o_rule.get("regex") or ""), q, re.IGNORECASE
        ):
            return "O"
        if any(k in q for k in (d_rule.get("keywords") or [])) or re.search(
            str(d_rule.get("regex") or ""), q, re.IGNORECASE
        ):
            return "D"
        if "RPN" in q.upper():
            return "RPN"
        return None

    def _try_answer_avg_metric_by_process_step(self, question: str) -> dict | None:
        """Deterministic answer for: '<设计项目> 的平均严重度/平均频度/平均探测度/平均RPN'."""
        metric = self._extract_avg_metric_from_question(question)
        if not metric:
            return None

        ps_key = self._extract_process_step_general(question)
        if not ps_key:
            return None

        matched_name = self._match_process_step_name(ps_key)
        if not matched_name:
            return None

        # 优先用 FailureMode 自身的数值字段（建图时写入），这是“按工序”最稳的口径。
        rows = self._query_params(
            f"""
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {{ProcessStep: $step}})
            WITH fd
            WHERE fd.{metric} IS NOT NULL
            RETURN avg(toFloat(fd.{metric})) AS avg_val, count(fd) AS n
            """.strip(),
            {"step": matched_name},
        )
        avg_val = rows[0].get("avg_val") if rows else None
        n = int(rows[0].get("n", 0)) if rows else 0

        if avg_val is None or n == 0:
            return None

        # 统一展示 2 位小数
        try:
            avg_num = float(avg_val)
        except Exception:
            return None

        metric_name = {
            "S": "严重度",
            "O": "频度数",
            "D": "探测度数",
            "RPN": "RPN",
        }.get(metric, metric)

        answer = f"{matched_name} 对应的{metric_name}平均值为 {avg_num:.2f}（n={n}）。"
        return {
            "answer": answer,
            "context": [f"ProcessStep={matched_name}", f"metric={metric}"],
            "context_raw": {"avg": avg_num, "n": n},
        }

    # ------------------------------
    # 全局/跨项目的确定性问答分支
    # ------------------------------
    @staticmethod
    def _extract_metric_any(question: str) -> str | None:
        q = (question or "")
        s_rule = METRIC_SYNONYMS.get("S", {})
        o_rule = METRIC_SYNONYMS.get("O", {})
        d_rule = METRIC_SYNONYMS.get("D", {})

        if any(k in q for k in (s_rule.get("keywords") or [])) or re.search(
            str(s_rule.get("regex") or ""), q, re.IGNORECASE
        ):
            return "S"
        if any(k in q for k in (o_rule.get("keywords") or [])) or re.search(
            str(o_rule.get("regex") or ""), q, re.IGNORECASE
        ):
            return "O"
        if any(k in q for k in (d_rule.get("keywords") or [])) or re.search(
            str(d_rule.get("regex") or ""), q, re.IGNORECASE
        ):
            return "D"
        if "RPN" in q.upper():
            return "RPN"
        return None

    def _try_answer_per_mode_metric_by_process_step(self, question: str) -> dict | None:
        """Deterministic answer for: 'X 对应的每个失效模式的 RPN/S/O/D 分别是多少'."""
        q = (question or "").strip()
        if not q:
            return None
        if "失效模式" not in q:
            return None
        if not ("分别" in q or "分别是" in q or "各" in q or "每个" in q):
            return None

        metric = self._extract_metric_any(q)
        if not metric:
            return None

        ps_key = self._extract_process_step_general(q)
        if not ps_key:
            return None
        matched_name = self._match_process_step_name(ps_key)
        if not matched_name:
            return None

        rows = self._query_params(
            f"""
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {{ProcessStep: $step}})
            WITH fd
            WHERE fd.{metric} IS NOT NULL
            RETURN fd.FailureMode AS FailureMode, toFloat(fd.{metric}) AS val
            ORDER BY fd.FailureMode
            """.strip(),
            {"step": matched_name},
        )
        items: list[dict[str, object]] = []
        for r in rows:
            fm = str(r.get("FailureMode") or "").strip()
            v = r.get("val")
            if not fm or v is None:
                continue
            try:
                vv = float(v)
            except Exception:
                continue
            items.append({"FailureMode": fm, metric: vv})

        if not items:
            return None

        metric_name = {"S": "严重度", "O": "频度数", "D": "探测度数", "RPN": "RPN"}.get(metric, metric)
        answer = f"{matched_name} 对应的每个失效模式的{metric_name}如下：" + "；".join(
            f"{it['FailureMode']}={int(it[metric]) if float(it[metric]).is_integer() else it[metric]}" for it in items
        )
        return {
            "answer": answer,
            "context": [f"ProcessStep={matched_name}", f"metric={metric}", "per_mode=1"],
            "context_raw": items,
        }

    def _try_answer_extreme_metric_mode_by_process_step(self, question: str) -> dict | None:
        """Deterministic answer for extreme metric questions.

        Examples:
        - X 对应的 RPN 最大/最小 的失效模式是哪些
        - X 对应的失效模式里，哪个探测度最高
        """
        q = (question or "").strip()
        if not q:
            return None
        if "失效模式" not in q:
            return None
        metric = self._extract_metric_any(q)
        if not metric:
            return None

        want_max = any(k in q for k in INTENT_SYNONYMS.get("max", []))
        want_min = any(k in q for k in INTENT_SYNONYMS.get("min", []))
        if not (want_max or want_min):
            return None

        ps_key = self._extract_process_step_general(q)
        if not ps_key:
            return None
        matched_name = self._match_process_step_name(ps_key)
        if not matched_name:
            return None

        agg_fn = "max" if want_max else "min"
        rows = self._query_params(
            f"""
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {{ProcessStep: $step}})
            WHERE fd.{metric} IS NOT NULL
            RETURN {agg_fn}(toFloat(fd.{metric})) AS extreme
            """.strip(),
            {"step": matched_name},
        )
        extreme = rows[0].get("extreme") if rows else None
        if extreme is None:
            return None
        try:
            extreme_val = float(extreme)
        except Exception:
            return None

        modes = self._query_params(
            f"""
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {{ProcessStep: $step}})
            WHERE fd.{metric} IS NOT NULL AND toFloat(fd.{metric}) = $v
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY fd.FailureMode
            """.strip(),
            {"step": matched_name, "v": extreme_val},
        )
        items = [str(r.get("FailureMode") or "").strip() for r in modes]
        items = [x for x in items if x]
        if not items:
            return None

        metric_name = {"S": "严重度", "O": "频度数", "D": "探测度数", "RPN": "RPN"}.get(metric, metric)
        word = "最大" if want_max else "最小"
        extreme_text = str(int(extreme_val)) if float(extreme_val).is_integer() else str(extreme_val)
        answer = f"{matched_name} 对应的{metric_name}{word}值为 {extreme_text}，对应失效模式：" + "，".join(items)
        return {
            "answer": answer,
            "context": [f"ProcessStep={matched_name}", f"metric={metric}", f"extreme={'max' if want_max else 'min'}"],
            "context_raw": {"value": extreme_val, "modes": items},
        }

    def _try_answer_modes_effects_causes_by_process_step(self, question: str) -> dict | None:
        """Deterministic answer for: 'X 对应的失效模式、后果、原因分别是什么（列出来）'."""
        q = (question or "").strip()
        if not q:
            return None
        if not ("失效模式" in q and ("后果" in q or "失效后果" in q) and ("原因" in q or "失效原因" in q)):
            return None

        ps_key = self._extract_process_step_general(q)
        if not ps_key:
            return None
        matched_name = self._match_process_step_name(ps_key)
        if not matched_name:
            return None

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {ProcessStep: $step})
            OPTIONAL MATCH (fd)-[:resultsInFailureEffect]->(fe:FailureEffect)
            OPTIONAL MATCH (fd)-[:isDueToFailureCause]->(fc:FailureCause)
            RETURN fd.FailureMode AS FailureMode,
                   collect(DISTINCT fe.FailureEffect) AS Effects,
                   collect(DISTINCT fc.FailureCause) AS Causes
            ORDER BY fd.FailureMode
            """.strip(),
            {"step": matched_name},
        )
        items: list[dict[str, object]] = []
        for r in rows:
            fm = str(r.get("FailureMode") or "").strip()
            if not fm:
                continue
            eff = [str(x).strip() for x in (r.get("Effects") or []) if str(x).strip()]
            cau = [str(x).strip() for x in (r.get("Causes") or []) if str(x).strip()]
            items.append({"FailureMode": fm, "FailureEffect": eff, "FailureCause": cau})

        if not items:
            return None

        # 只生成简洁文本；详细数据放 context_raw
        parts = []
        for it in items:
            eff = " / ".join(it["FailureEffect"]) if it["FailureEffect"] else ""
            cau = " / ".join(it["FailureCause"]) if it["FailureCause"] else ""
            parts.append(f"{it['FailureMode']}（后果：{eff or '无'}；原因：{cau or '无'}）")
        answer = f"{matched_name} 对应的失效模式/后果/原因如下：" + "；".join(parts)
        return {
            "answer": answer,
            "context": [f"ProcessStep={matched_name}", "modes_effects_causes=1"],
            "context_raw": items,
        }

    # 参数：question(str)；返回：dict（包含 answer/answer_file/context/context_raw）；功能：完整问答流程：先让模型生成 Cypher 并查图，查不到再走向量检索，最后让模型基于上下文生成中文答案。
