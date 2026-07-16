# -*- coding: utf-8 -*-

# 该文件承载“全局极值/排序/对比”相关的规则化问答分支。

import re
from synonyms import INTENT_SYNONYMS


class DeterministicGlobalExtremeMixin:
    @staticmethod
    def _extract_two_quoted_names(question: str) -> tuple[str, str] | None:
        names = re.findall(r"“([^”]+)”", question or "")
        if len(names) >= 2:
            a = str(names[0]).strip()
            b = str(names[1]).strip()
            if a and b:
                return a, b
        return None

    @staticmethod
    def _extract_extreme_followup_slot(question: str) -> str | None:
        """Detect secondary target in questions like 'RPN最高的失效模式，其X是什么'."""
        q = (question or "").strip()
        if not q:
            return None

        # 先识别更具体的控制类关键词，避免被“措施”泛词误判。
        if any(k in q for k in ("临时措施", "临时采取", "临时/改进措施", "临时改进措施", "改进措施")):
            return "temp"
        if any(k in q for k in ("探测性设计控制", "探测性控制", "探测措施", "探测控制")):
            return "detect"
        if any(k in q for k in ("预防性设计控制", "预防性控制", "预防措施", "预防控制")):
            return "prevent"
        if any(k in q for k in ("现行设计控制措施", "设计控制措施", "设计控制")):
            return "design_controls"
        if any(k in q for k in ("失效后果", "后果", "影响")):
            return "effect"
        if any(k in q for k in ("失效原因", "原因")):
            return "cause"
        return None

    def _query_global_extreme_modes(self, metric: str, want_max: bool) -> tuple[float, list[str]] | None:
        if metric not in {"S", "O", "D", "RPN"}:
            return None
        agg_fn = "max" if want_max else "min"
        rows = self._query_params(
            f"""
            MATCH (fd:FailureMode)
            WHERE fd.{metric} IS NOT NULL
            RETURN {agg_fn}(toFloat(fd.{metric})) AS extreme
            """.strip(),
            {},
        )
        extreme = rows[0].get("extreme") if rows else None
        if extreme is None:
            return None
        try:
            extreme_val = float(extreme)
        except Exception:
            return None

        rows2 = self._query_params(
            f"""
            MATCH (fd:FailureMode)
            WHERE fd.{metric} IS NOT NULL AND toFloat(fd.{metric}) = $v
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY FailureMode
            """.strip(),
            {"v": extreme_val},
        )
        modes = sorted({str(r.get("FailureMode") or "").strip() for r in rows2 if str(r.get("FailureMode") or "").strip()})
        if not modes:
            return None
        return extreme_val, modes

    @staticmethod
    def _format_mode_value_parts(mode_to_values: dict[str, set[str]]) -> list[str]:
        parts: list[str] = []
        for mode in sorted(mode_to_values.keys()):
            vals = sorted({v for v in mode_to_values.get(mode, set()) if v})
            if vals:
                parts.append(f"{mode}：" + "，".join(vals))
        return parts

    def _try_answer_global_extreme_mode_followup(self, question: str) -> dict | None:
        """Handle compound intent: extreme metric mode + requested follow-up field.

        Example: 针对RPN最高的失效模式，其临时采取的措施是什么？
        """
        q = (question or "").strip()
        if not q:
            return None

        metric = self._extract_metric_any(q)
        if not metric:
            return None

        want_max = any(k in q for k in INTENT_SYNONYMS.get("max", []))
        want_min = any(k in q for k in INTENT_SYNONYMS.get("min", []))
        if not (want_max or want_min):
            return None

        slot = self._extract_extreme_followup_slot(q)
        if not slot:
            return None

        # 这类问题必须有“失效模式”对象，否则容易误伤其它统计问句。
        if "失效模式" not in q:
            return None

        extreme_pack = self._query_global_extreme_modes(metric, want_max=want_max)
        if not extreme_pack:
            return None
        extreme_val, modes = extreme_pack

        # 失效模式 -> 字段值集合
        mode_to_values: dict[str, set[str]] = {m: set() for m in modes}

        if slot == "temp":
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.FailureMode IN $modes
                RETURN fd.FailureMode AS FailureMode, toString(fd.TempMeasure) AS v
                """.strip(),
                {"modes": modes},
            )
            for r in rows:
                m = str(r.get("FailureMode") or "").strip()
                v = str(r.get("v") or "").strip()
                if m in mode_to_values and v and v.lower() != "nan":
                    mode_to_values[m].add(v)

            # 兼容旧图：若图中无 TempMeasure，则回落到默认 CSV。
            if not any(mode_to_values.values()):
                df = self._get_default_dfmea_df()
                if df is not None and {"FailureMode", "TempMeasure"}.issubset(set(df.columns)):
                    s_mode = df["FailureMode"].fillna("").astype(str)
                    s_temp = df["TempMeasure"].fillna("").astype(str)
                    for mode in modes:
                        mask = s_mode.eq(mode) | s_mode.str.contains(re.escape(mode), na=False)
                        vals = [x.strip() for x in s_temp.loc[mask].tolist() if x and str(x).strip() and str(x).strip().lower() != "nan"]
                        if vals:
                            mode_to_values[mode].update(vals)

            parts = self._format_mode_value_parts(mode_to_values)
            slot_label = "临时采取的措施"

        elif slot == "prevent":
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.FailureMode IN $modes
                RETURN fd.FailureMode AS FailureMode, toString(fd.PreventControl) AS v
                """.strip(),
                {"modes": modes},
            )
            for r in rows:
                m = str(r.get("FailureMode") or "").strip()
                v = str(r.get("v") or "").strip()
                if m in mode_to_values and v and v.lower() != "nan":
                    mode_to_values[m].add(v)
            parts = self._format_mode_value_parts(mode_to_values)
            slot_label = "预防性设计控制"

        elif slot == "detect":
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.FailureMode IN $modes
                RETURN fd.FailureMode AS FailureMode, toString(fd.DetectionMeasure) AS v
                """.strip(),
                {"modes": modes},
            )
            for r in rows:
                m = str(r.get("FailureMode") or "").strip()
                v = str(r.get("v") or "").strip()
                if m in mode_to_values and v and v.lower() != "nan":
                    mode_to_values[m].add(v)
            parts = self._format_mode_value_parts(mode_to_values)
            slot_label = "探测性设计控制"

        elif slot == "design_controls":
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.FailureMode IN $modes
                RETURN fd.FailureMode AS FailureMode,
                       toString(fd.PreventControl) AS p,
                       toString(fd.DetectionMeasure) AS d
                """.strip(),
                {"modes": modes},
            )
            parts = []
            for mode in modes:
                pvals: set[str] = set()
                dvals: set[str] = set()
                for r in rows:
                    m = str(r.get("FailureMode") or "").strip()
                    if m != mode:
                        continue
                    pv = str(r.get("p") or "").strip()
                    dv = str(r.get("d") or "").strip()
                    if pv and pv.lower() != "nan":
                        pvals.add(pv)
                    if dv and dv.lower() != "nan":
                        dvals.add(dv)
                if pvals or dvals:
                    ptxt = "，".join(sorted(pvals)) if pvals else "未记录"
                    dtxt = "，".join(sorted(dvals)) if dvals else "未记录"
                    parts.append(f"{mode}：预防={ptxt}；探测={dtxt}")
            slot_label = "现行设计控制措施"

        elif slot == "effect":
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)-[:resultsInFailureEffect]->(fe:FailureEffect)
                WHERE fd.FailureMode IN $modes
                RETURN fd.FailureMode AS FailureMode, toString(fe.FailureEffect) AS v
                """.strip(),
                {"modes": modes},
            )
            for r in rows:
                m = str(r.get("FailureMode") or "").strip()
                v = str(r.get("v") or "").strip()
                if m in mode_to_values and v and v.lower() != "nan":
                    mode_to_values[m].add(v)
            parts = self._format_mode_value_parts(mode_to_values)
            slot_label = "失效后果"

        else:  # slot == "cause"
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)-[:isDueToFailureCause]->(fc:FailureCause)
                WHERE fd.FailureMode IN $modes
                RETURN fd.FailureMode AS FailureMode, toString(fc.FailureCause) AS v
                """.strip(),
                {"modes": modes},
            )
            for r in rows:
                m = str(r.get("FailureMode") or "").strip()
                v = str(r.get("v") or "").strip()
                if m in mode_to_values and v and v.lower() != "nan":
                    mode_to_values[m].add(v)
            parts = self._format_mode_value_parts(mode_to_values)
            slot_label = "失效原因"

        metric_name = {"S": "严重度(S)", "O": "频度数(O)", "D": "探测度(D)", "RPN": "RPN"}.get(metric, metric)
        word = "最高" if want_max else "最低"
        vtxt = str(int(extreme_val)) if float(extreme_val).is_integer() else str(extreme_val)
        mode_txt = "，".join(modes)

        if not parts:
            answer = f"按{metric_name}看，全局{word}值为 {vtxt}，对应失效模式：{mode_txt}；但文档中未记录其{slot_label}。"
        else:
            answer = f"按{metric_name}看，全局{word}值为 {vtxt}，对应失效模式：{mode_txt}；其{slot_label}如下：" + "；".join(parts) + "。"

        return {
            "answer": answer,
            "context": [
                "scope=global",
                f"metric={metric}",
                f"extreme={'max' if want_max else 'min'}",
                f"slot={slot}",
            ],
            "context_raw": {
                "value": extreme_val,
                "modes": modes,
                "slot": slot,
                "mode_values": {k: sorted(v) for k, v in mode_to_values.items()},
            },
        }

    def _try_answer_global_extreme_rpn(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "RPN" not in q.upper():
            return None
        if "失效模式" not in q:
            return None

        want_max = any(k in q for k in INTENT_SYNONYMS.get("max", []))
        want_min = any(k in q for k in INTENT_SYNONYMS.get("min", []))
        if not (want_max or want_min):
            return None

        agg_fn = "max" if want_max else "min"
        rows = self._query_params(
            f"""
            MATCH (fd:FailureMode)
            WHERE fd.RPN IS NOT NULL
            RETURN {agg_fn}(toFloat(fd.RPN)) AS extreme
            """.strip(),
            {},
        )
        extreme = rows[0].get("extreme") if rows else None
        if extreme is None:
            return None
        try:
            extreme_val = float(extreme)
        except Exception:
            return None

        rows2 = self._query_params(
            """
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
            WHERE fd.RPN IS NOT NULL AND toFloat(fd.RPN) = $v
            RETURN DISTINCT fd.FailureMode AS FailureMode, ps.ProcessStep AS ProcessStep
            ORDER BY ps.ProcessStep, fd.FailureMode
            """.strip(),
            {"v": extreme_val},
        )
        items: list[dict[str, object]] = []
        modes: list[str] = []
        for r in rows2:
            fm = str(r.get("FailureMode") or "").strip()
            ps = str(r.get("ProcessStep") or "").strip()
            if fm:
                modes.append(fm)
            if fm and ps:
                items.append({"FailureMode": fm, "ProcessStep": ps, "RPN": extreme_val})
        modes = sorted({m for m in modes if m})
        if not modes:
            return None

        word = "最高" if want_max else "最低"
        vtxt = str(int(extreme_val)) if float(extreme_val).is_integer() else str(extreme_val)
        answer = f"按RPN看，全局风险{word}值为 {vtxt}，对应失效模式：" + "，".join(modes)
        return {
            "answer": answer,
            "context": [f"metric=RPN", f"extreme={'max' if want_max else 'min'}", "scope=global"],
            "context_raw": {"value": extreme_val, "modes": modes, "rows": items},
        }

    def _try_answer_global_extreme_metric_modes(self, question: str) -> dict | None:
        """Deterministic answer for global extreme (max/min) of S/O/D/RPN on FailureMode.

        Examples:
        - 根据RPN数值，目前风险最高... 失效模式是什么（RPN max）
        - 频度数(O)最高的失效模式有哪些
        - 探测度(D)最高的失效模式有哪些
        """
        q = (question or "").strip()
        if not q:
            return None
        if "失效模式" not in q:
            return None
        # 复合问句（如“最高失效模式的临时措施是什么”）由专用分支处理，避免只答前半句。
        if self._extract_extreme_followup_slot(q):
            return None
        # “平均X最高”类问题应走“项目均值对比”，不要误判为“单条极值”。
        if "平均" in q:
            return None
        # 项目内/设计项目内的极值，交给按项目分支处理，避免误答成全局极值。
        if self._extract_process_step_general(q):
            return None

        metric = self._extract_metric_any(q)
        if not metric:
            return None

        want_max = any(k in q for k in INTENT_SYNONYMS.get("max", []))
        want_min = any(k in q for k in INTENT_SYNONYMS.get("min", []))
        if not (want_max or want_min):
            return None

        agg_fn = "max" if want_max else "min"
        rows = self._query_params(
            f"""
            MATCH (fd:FailureMode)
            WHERE fd.{metric} IS NOT NULL
            RETURN {agg_fn}(toFloat(fd.{metric})) AS extreme
            """.strip(),
            {},
        )
        extreme = rows[0].get("extreme") if rows else None
        if extreme is None:
            return None
        try:
            extreme_val = float(extreme)
        except Exception:
            return None

        rows2 = self._query_params(
            f"""
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
            WHERE fd.{metric} IS NOT NULL AND toFloat(fd.{metric}) = $v
            RETURN DISTINCT fd.FailureMode AS FailureMode, ps.ProcessStep AS ProcessStep
            ORDER BY ps.ProcessStep, fd.FailureMode
            """.strip(),
            {"v": extreme_val},
        )
        modes = sorted({str(r.get("FailureMode") or "").strip() for r in rows2 if str(r.get("FailureMode") or "").strip()})
        if not modes:
            return None

        metric_name = {"S": "严重度(S)", "O": "频度数(O)", "D": "探测度(D)", "RPN": "RPN"}.get(metric, metric)
        word = "最高" if want_max else "最低"
        vtxt = str(int(extreme_val)) if float(extreme_val).is_integer() else str(extreme_val)
        answer = f"按{metric_name}看，全局{word}值为 {vtxt}，对应失效模式：" + "，".join(modes)
        return {
            "answer": answer,
            "context": [f"metric={metric}", f"extreme={'max' if want_max else 'min'}", "scope=global"],
            "context_raw": {"value": extreme_val, "modes": modes},
        }

    def _try_answer_global_top_rpn_with_project(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "RPN排名前五" not in q and "RPN" not in q.upper():
            return None
        if "排名前五" not in q and "前五" not in q:
            return None
        if "失效模式" not in q:
            return None

        # 先取前 5 的“阈值”，再把与第 5 名并列的也一起返回，避免并列导致“第五名是谁”不唯一。
        top5 = self._query_params(
            """
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
            WHERE fd.RPN IS NOT NULL
            RETURN fd.FailureMode AS FailureMode, ps.ProcessStep AS ProcessStep, toFloat(fd.RPN) AS RPN
            ORDER BY RPN DESC
            LIMIT 5
            """.strip(),
            {},
        )
        if not top5:
            return None
        try:
            cutoff = min(float(r.get("RPN")) for r in top5 if r.get("RPN") is not None)
        except Exception:
            return None

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
            WHERE fd.RPN IS NOT NULL AND toFloat(fd.RPN) >= $cutoff
            RETURN fd.FailureMode AS FailureMode, ps.ProcessStep AS ProcessStep, toFloat(fd.RPN) AS RPN
            ORDER BY RPN DESC, ps.ProcessStep ASC, fd.FailureMode ASC
            """.strip(),
            {"cutoff": cutoff},
        )

        items: list[dict[str, object]] = []
        parts: list[str] = []
        for i, r in enumerate(rows, start=1):
            fm = str(r.get("FailureMode") or "").strip()
            ps = str(r.get("ProcessStep") or "").strip()
            v = r.get("RPN")
            if not fm or v is None:
                continue
            try:
                vv = float(v)
            except Exception:
                continue
            items.append({"FailureMode": fm, "ProcessStep": ps, "RPN": vv})
            vtxt = str(int(vv)) if float(vv).is_integer() else str(vv)
            parts.append(f"{i}) {fm}（项目：{ps}，RPN={vtxt}）")

        if not items:
            return None
        answer = "RPN 排名前五（含并列）的失效模式如下：" + "；".join(parts)
        return {
            "answer": answer,
            "context": ["metric=RPN", "top=5+tied", "scope=global"],
            "context_raw": items,
        }

    def _try_answer_global_rpn_threshold_list(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "RPN" not in q.upper() or "失效模式" not in q:
            return None

        m = re.search(r"RPN\s*值?\s*(超过|高于|大于|低于|小于)\s*(\d+(?:\.\d+)?)", q)
        if not m:
            return None
        op = m.group(1)
        thr = float(m.group(2))
        want_gt = op in ("超过", "高于", "大于")

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.RPN IS NOT NULL
            WITH fd, toFloat(fd.RPN) AS v
            WHERE (v > $thr AND $want_gt = true) OR (v < $thr AND $want_gt = false)
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY fd.FailureMode
            """.strip(),
            {"thr": thr, "want_gt": want_gt},
        )
        items = [str(r.get("FailureMode") or "").strip() for r in rows]
        items = [x for x in items if x]
        if not items:
            return None

        word = "超过" if want_gt else "低于"
        ttxt = str(int(thr)) if float(thr).is_integer() else str(thr)
        answer = f"所有 RPN 值{word} {ttxt} 的失效模式如下：" + "，".join(items)
        return {
            "answer": answer,
            "context": ["metric=RPN", f"threshold={word}{ttxt}", "scope=global"],
            "context_raw": items,
        }

    def _try_answer_project_max_avg_metric(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "哪个" not in q or "设计项目" not in q or "平均" not in q or "最高" not in q:
            return None
        metric = self._extract_avg_metric_from_question(q)
        if not metric:
            return None

        rows = self._query_params(
            f"""
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
            WHERE fd.{metric} IS NOT NULL
            WITH ps.ProcessStep AS ProcessStep, avg(toFloat(fd.{metric})) AS avg_val, count(fd) AS n
            RETURN ProcessStep, avg_val, n
            ORDER BY avg_val DESC, n DESC, ProcessStep ASC
            LIMIT 1
            """.strip(),
            {},
        )
        if not rows:
            return None
        ps = str(rows[0].get("ProcessStep") or "").strip()
        avg_val = rows[0].get("avg_val")
        n = int(rows[0].get("n", 0) or 0)
        if not ps or avg_val is None or n <= 0:
            return None
        try:
            av = float(avg_val)
        except Exception:
            return None

        metric_name = {"S": "严重度(S)", "O": "频度数(O)", "D": "探测度(D)", "RPN": "RPN"}.get(metric, metric)
        answer = f"平均{metric_name}最高的设计项目是：{ps}（平均值={av:.2f}，n={n}）。"
        return {
            "answer": answer,
            "context": ["scope=global", f"metric={metric}", "agg=avg", "argmax=1"],
            "context_raw": {"ProcessStep": ps, "avg": av, "n": n},
        }

    def _try_answer_compare_two_projects_avg_rpn(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "比较" not in q or "平均RPN" not in q:
            return None
        names = self._extract_two_quoted_names(q)
        if not names:
            return None
        a, b = names

        rows = self._query_params(
            """
            UNWIND $steps AS step
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {ProcessStep: step})
            WHERE fd.RPN IS NOT NULL
            RETURN step AS ProcessStep, avg(toFloat(fd.RPN)) AS avg_val, count(fd) AS n
            """.strip(),
            {"steps": [a, b]},
        )
        mp = {str(r.get("ProcessStep") or "").strip(): r for r in rows or []}
        if a not in mp or b not in mp:
            return None
        try:
            av_a = float(mp[a].get("avg_val"))
            av_b = float(mp[b].get("avg_val"))
        except Exception:
            return None
        winner = a if av_a >= av_b else b
        answer = f"{a} 的平均RPN为 {av_a:.2f}；{b} 的平均RPN为 {av_b:.2f}。平均RPN更高的是：{winner}。"
        return {
            "answer": answer,
            "context": ["scope=global", "metric=RPN", "compare=2"],
            "context_raw": {a: av_a, b: av_b, "winner": winner},
        }
