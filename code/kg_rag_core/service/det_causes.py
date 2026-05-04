# -*- coding: utf-8 -*-

# 该文件承载失效原因语义归类与原因反查失效模式相关的规则化问答分支。

import re
from synonyms import CAUSE_SEMANTIC_SYNONYMS


class DeterministicCausesMixin:
    def _try_answer_failure_causes_by_prevent_control(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "预防措施" not in q:
            return None
        if "失效原因" not in q:
            return None

        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:isDueToFailureCause]->(fc:FailureCause)
            WHERE fd.PreventControl IS NOT NULL
              AND trim(toString(fd.PreventControl)) <> ''
              AND toString(fd.PreventControl) CONTAINS $kw
            RETURN DISTINCT fc.FailureCause AS FailureCause
            ORDER BY FailureCause
            """.strip(),
            {"kw": kw},
        )
        items = [str(r.get("FailureCause") or "").strip() for r in rows]
        items = [x for x in items if x]
        if not items:
            # 旧图回退：预防控制可能只存在于 FailureMeasure 文本中。
            rows2 = self._query_params(
                """
                MATCH (fd:FailureMode)-[:isDueToFailureCause]->(fc:FailureCause)-[:isImprovedByFailureMeasure]->(fm:FailureMeasure)
                WHERE fm.FailureMeasure IS NOT NULL
                  AND toString(fm.FailureMeasure) CONTAINS '预防控制：'
                  AND toString(fm.FailureMeasure) CONTAINS $kw
                RETURN DISTINCT fc.FailureCause AS FailureCause
                ORDER BY FailureCause
                """.strip(),
                {"kw": kw},
            )
            items = [str(r.get("FailureCause") or "").strip() for r in rows2]
            items = [x for x in items if x]
            if not items:
                return None

        if len(items) == 1:
            answer = f"“{kw}”这一预防措施主要是为了防止的失效原因是：{items[0]}。"
        else:
            answer = f"“{kw}”这一预防措施主要关联/防止的失效原因包括：" + "，".join(items) + "。"

        return {
            "answer": answer,
            "context": ["scope=global", f"prevent_kw={kw}", "list=causes"],
            "context_raw": items,
        }

    @staticmethod
    def _extract_cause_semantic_terms(question: str) -> list[str]:
        q = (question or "").strip()
        if not q or "失效原因" not in q:
            return []

        terms: list[str] = []

        # 优先提取引号中的语义词
        quoted_terms = [str(x).strip() for x in re.findall(r"[“\"]([^”\"]+)[”\"]", q)]
        terms.extend(quoted_terms)

        # 无引号兜底：属于/涉及/指向/相关 + 语义词
        # 有引号时通常语义边界更准确，不再用兜底模式追加，避免产生“了xxx”噪声词。
        if not quoted_terms:
            m = re.search(r"(?:属于|涉及|指向|明确指向|相关)(.+?)(?:的?失效原因|[？?])", q)
            if m:
                raw = str(m.group(1) or "").strip(" ，,。；;：:")
                if raw:
                    terms.extend([x.strip() for x in re.split(r"(?:或)|(?:或者)|(?:和)|(?:及)|(?:与)|[、,，/；;]", raw) if x.strip()])

        # 去掉常见功能词
        cleaned: list[str] = []
        seen: set[str] = set()
        stop_fragments = ("明确", "主要", "哪些", "什么", "类别", "类型")
        for t in terms:
            s = str(t or "").strip().strip("“”\"'‘’")
            for w in stop_fragments:
                s = s.replace(w, "")
            s = s.strip()
            if len(s) < 2:
                continue
            if s in seen:
                continue
            seen.add(s)
            cleaned.append(s)
        return cleaned

    @staticmethod
    def _expand_cause_semantic_keywords(term: str) -> list[str]:
        t = re.sub(r"\s+", "", str(term or "")).strip()
        if not t:
            return []

        kws: list[str] = [t]

        for canon, cfg in CAUSE_SEMANTIC_SYNONYMS.items():
            aliases = [canon] + list(cfg.get("aliases") or [])
            if any(a and (a in t or t in a) for a in aliases):
                kws.extend(aliases)
                kws.extend(list(cfg.get("keywords") or []))

        # 通用语义扩展：避免只修当前 3 个点
        if any(k in t for k in ("算法", "软件", "程序", "鲁棒", "逻辑", "编写")):
            kws.extend(["算法", "SOC算法", "BMS", "软件", "程序", "控制系统"])
        if any(k in t for k in ("环境", "温度", "风", "湿", "灰尘", "进水", "外界")):
            kws.extend(["环境温度", "通风", "风扇", "灰尘", "进水", "潮湿", "凝露", "功率过高"])
        if any(k in t for k in ("用户", "操作", "误操作", "违规", "使用不当")):
            kws.extend(["违规操作", "安装不规范", "负载未断开", "未压紧", "连接错误", "未明确区分正负极", "使用电流高于额定电流"])
        if any(k in t for k in ("干扰", "电磁", "外力", "碰撞", "震动", "挤压")):
            kws.extend(["电磁干扰", "干扰", "外力损伤", "碰撞", "震动", "挤压"])

        out: list[str] = []
        seen: set[str] = set()
        for k in kws:
            s = re.sub(r"\s+", "", str(k or "")).strip()
            if len(s) < 2:
                continue
            if s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    def _try_answer_failure_causes_by_semantic_category(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q or "失效原因" not in q:
            return None
        if not any(k in q for k in ("哪些", "属于", "涉及", "指向", "相关")):
            return None

        terms = self._extract_cause_semantic_terms(q)
        if not terms:
            return None

        rows = self._query_params(
            """
            MATCH (fc:FailureCause)
            RETURN DISTINCT fc.FailureCause AS FailureCause
            ORDER BY FailureCause
            """.strip(),
            {},
        )
        causes = [str(r.get("FailureCause") or "").strip() for r in rows]
        causes = [c for c in causes if c]
        if not causes:
            return None

        # 多语义词采用并集：A 或 B
        keyword_union: list[str] = []
        for t in terms:
            keyword_union.extend(self._expand_cause_semantic_keywords(t))

        def _match(cause: str) -> bool:
            c = re.sub(r"\s+", "", str(cause or ""))
            return any(k in c for k in keyword_union if k)

        items = [c for c in causes if _match(c)]

        # 结果去重 + 稳定排序
        items = sorted(set(items))
        if not items:
            return None

        if len(terms) == 1:
            answer = f"明确指向“{terms[0]}”的失效原因包括：" + "；".join(items) + "。"
        else:
            answer = f"涉及“{'”或“'.join(terms)}”的失效原因包括：" + "；".join(items) + "。"

        return {
            "answer": answer,
            "context": ["scope=global", f"cause_semantic={','.join(terms)}", "list=causes"],
            "context_raw": items,
        }

    def _try_answer_modes_by_cause_keyword(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "原因" not in q or "失效模式" not in q:
            return None
        if not ("出现在哪些" in q or "出现在哪些不同" in q):
            return None
        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:isDueToFailureCause]->(fc:FailureCause)
            WHERE fc.FailureCause CONTAINS $kw
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY FailureMode
            """.strip(),
            {"kw": kw},
        )
        items = [str(r.get("FailureMode") or "").strip() for r in rows]
        items = [x for x in items if x]
        if not items:
            return None
        answer = f"原因包含“{kw}”的失效模式包括：" + "，".join(items)
        return {
            "answer": answer,
            "context": ["scope=global", f"cause_kw={kw}", "list=modes"],
            "context_raw": items,
        }

    def _try_answer_modes_by_cause_phrase_quoted(self, question: str) -> dict | None:
        """Deterministic answer for: given a quoted cause phrase, return related failure mode(s).

        Targets questions like:
        - “X”会导致什么后果？
        - “X”具体指哪个失效模式？
        - “X”被列为哪些失效模式的原因？

        This is intentionally strict to avoid hijacking analytical questions.
        """

        q = (question or "").strip()
        if not q:
            return None

        # 必须包含引号短语。
        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        cause = str(kws[0]).strip()
        if not cause:
            return None

        # 候选原因集合（先从用户原始短语开始）。
        cause_candidates = [cause]

        # 仅处理“原因 -> 失效模式”这类特定意图。
        intent_markers = (
            "会导致什么后果",
            "导致什么后果",
            "指哪个失效模式",
            "具体指哪个失效模式",
            "对应的失效",
            "被列为哪些失效模式的原因",
            "哪些失效模式的原因",
        )
        if not any(m in q for m in intent_markers):
            return None

        def _lookup_modes_by_causes(tries: list[str]) -> tuple[list[str], str | None]:
            # 1) 优先精确匹配，避免 CONTAINS 过宽匹配。
            for c in tries:
                rows = self._query_params(
                    """
                    MATCH (fd:FailureMode)-[:isDueToFailureCause]->(fc:FailureCause)
                    WHERE fc.FailureCause = $cause
                    RETURN DISTINCT fd.FailureMode AS FailureMode
                    ORDER BY FailureMode
                    """.strip(),
                    {"cause": c},
                )
                items = [str(r.get("FailureMode") or "").strip() for r in rows]
                items = [x for x in items if x]
                if items:
                    return items, c

            # 2) 回退到子串匹配。
            for c in tries:
                rows = self._query_params(
                    """
                    MATCH (fd:FailureMode)-[:isDueToFailureCause]->(fc:FailureCause)
                    WHERE fc.FailureCause CONTAINS $cause
                    RETURN DISTINCT fd.FailureMode AS FailureMode
                    ORDER BY FailureMode
                    """.strip(),
                    {"cause": c},
                )
                items = [str(r.get("FailureMode") or "").strip() for r in rows]
                items = [x for x in items if x]
                if items:
                    return items, c

            return [], None

        items, resolved_cause = _lookup_modes_by_causes(cause_candidates)

        # 若仍未命中，则把用户泛化短语做确定性“近似映射”，
        # 映射到当前图中最接近的 FailureCause。
        if not items:
            def _norm_text(s: str) -> str:
                s = (s or "").strip()
                s = re.sub(r"[\s,，。\.；;:：、/\\]+", "", s)
                for w in [
                    "不合理",
                    "异常",
                    "不良",
                    "损坏",
                    "失效",
                    "故障",
                    "问题",
                    "不足",
                    "不工作",
                    "未工作",
                    "不受控制",
                    "不受控",
                ]:
                    s = s.replace(w, "")
                # 图中常写作 BMS/SOC 算法，但用户可能说“软件算法”
                s = s.replace("软件", "")
                return s

            def _bigrams(s: str) -> set[str]:
                if not s:
                    return set()
                if len(s) == 1:
                    return {s}
                return {s[i : i + 2] for i in range(len(s) - 1)}

            def _jaccard(a: set[str], b: set[str]) -> float:
                if not a or not b:
                    return 0.0
                inter = len(a & b)
                union = len(a | b)
                return inter / union if union else 0.0

            def _focus_keywords(user_phrase: str) -> list[str]:
                t = user_phrase or ""
                kws: list[str] = []
                if ("算法" in t) or ("软件" in t) or ("程序" in t):
                    kws += ["算法", "SOC", "BMS", "软件", "程序"]
                if ("元器件" in t) or ("器件" in t):
                    kws += ["元器件", "器件"]
                if "风扇" in t:
                    kws += ["风扇"]
                seen = set()
                out: list[str] = []
                for k in kws:
                    if k not in seen:
                        seen.add(k)
                        out.append(k)
                return out

            focus = _focus_keywords(cause)
            if focus:
                rows = self._query_params(
                    """
                    MATCH (fc:FailureCause)
                    RETURN DISTINCT fc.FailureCause AS cause
                    """.strip(),
                    {},
                )
                all_causes = [str(r.get("cause") or "").strip() for r in rows]
                all_causes = [c for c in all_causes if c]

                # 先按焦点关键词筛选，降低误匹配。
                filtered = [c for c in all_causes if any(k in c for k in focus)]
                if not filtered:
                    filtered = all_causes

                u = _norm_text(cause)
                u_bg = _bigrams(u)
                scored: list[tuple[float, str]] = []
                for c in filtered:
                    c_norm = _norm_text(c)
                    s = _jaccard(u_bg, _bigrams(c_norm))
                    if any(k in c for k in focus):
                        s += 0.05
                    scored.append((s, c))
                scored.sort(key=lambda x: x[0], reverse=True)

                # 采用保守阈值，避免错误自动映射。
                mapped = [c for s, c in scored if s >= 0.15][:5]
                if mapped:
                    items, resolved_cause = _lookup_modes_by_causes(mapped)

        if not items:
            return None

        if len(items) == 1:
            answer = f"{items[0]}。"
        else:
            answer = "对应的失效模式包括：" + "，".join(items)

        ctx = ["scope=global", f"cause_phrase={cause}", "mode_lookup=by_cause"]
        if resolved_cause and resolved_cause != cause:
            ctx.append(f"cause_resolved={resolved_cause}")
        return {"answer": answer, "context": ctx, "context_raw": items}

