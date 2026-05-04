# -*- coding: utf-8 -*-

# 该文件承载失效后果/严重度相关的规则化问答分支。

import re
from synonyms import INTENT_SYNONYMS


class DeterministicEffectsMixin:
    def _try_answer_modes_by_severity(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q or "严重度" not in q or "失效模式" not in q:
            return None
        m = re.search(r"严重度\s*\(?S\)?\s*为\s*(\d+)\s*分?", q)
        if not m:
            return None
        sev = int(m.group(1))
        if sev < 0 or sev > 10:
            return None
        rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.S IS NOT NULL AND toInteger(toFloat(fd.S)) = $s
            RETURN DISTINCT fd.FailureMode AS FailureMode, toFloat(fd.RPN) AS RPN
            ORDER BY fd.FailureMode
            """.strip(),
            {"s": sev},
        )
        modes: list[str] = []
        rpns: list[float] = []
        for r in rows:
            fm = str(r.get("FailureMode") or "").strip()
            if fm:
                modes.append(fm)
            v = r.get("RPN")
            if v is not None:
                try:
                    rpns.append(float(v))
                except Exception:
                    pass
        modes = [x for x in modes if x]
        if not modes:
            return None
        dist = ""
        if rpns:
            dist = f"RPN分布：min={min(rpns):.0f}，max={max(rpns):.0f}，avg={sum(rpns)/len(rpns):.2f}"  # noqa: E501
        answer = f"严重度(S)={sev} 的失效模式共有 {len(modes)} 项：" + "，".join(modes)
        if dist:
            answer += "。" + dist + "。"
        return {
            "answer": answer,
            "context": ["scope=global", f"S={sev}"],
            "context_raw": {"S": sev, "modes": modes, "rpn_values": rpns},
        }

    def _try_answer_effects_and_modes_by_severity(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "严重度" not in q or "失效后果" not in q:
            return None
        m = re.search(r"严重度\s*\(?S\)?\s*为\s*(\d+)\s*分?", q)
        if not m:
            return None
        sev = int(m.group(1))
        if sev < 0 or sev > 10:
            return None

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:resultsInFailureEffect]->(fe:FailureEffect)
            WHERE fd.S IS NOT NULL AND toInteger(toFloat(fd.S)) = $s
            RETURN fe.FailureEffect AS FailureEffect, collect(DISTINCT fd.FailureMode) AS Modes
            ORDER BY fe.FailureEffect
            """.strip(),
            {"s": sev},
        )
        items: list[dict[str, object]] = []
        all_modes: list[str] = []
        parts: list[str] = []
        for r in rows:
            eff = str(r.get("FailureEffect") or "").strip()
            modes = [str(x).strip() for x in (r.get("Modes") or []) if str(x).strip()]
            if not eff and not modes:
                continue
            if modes:
                all_modes.extend(modes)
            items.append({"FailureEffect": eff, "FailureModes": sorted(set(modes))})
            if eff:
                modes_txt = "，".join(sorted(set(modes))) if modes else "（无）"
                parts.append(f"{eff} ← {modes_txt}")

        all_modes = sorted(set(all_modes))
        if not items and not all_modes:
            return None

        if parts:
            answer = f"严重度(S)={sev} 的失效后果及其对应失效模式如下：" + "；".join(parts)
        else:
            answer = f"严重度(S)={sev} 的对应失效模式：" + "，".join(all_modes)
        return {
            "answer": answer,
            "context": ["scope=global", f"S={sev}", "effects=1"],
            "context_raw": {"S": sev, "items": items, "modes": all_modes},
        }

    def _try_answer_modes_by_effect_double_contains(self, question: str) -> dict | None:
        """Deterministic answer for: '哪些失效模式的后果描述中同时包含A和B'.

        规则：严格按字面匹配（Cypher CONTAINS），不做同义词扩展；即使 0 命中也要直接返回“无”，
        避免落入 LLM/RAG 语义推断导致偏离题意。
        """

        q = (question or "").strip()
        if not q:
            return None

        if "失效模式" not in q:
            return None
        if not ("后果" in q or "失效后果" in q or "后果描述" in q):
            return None
        if not any(p in q for p in INTENT_SYNONYMS.get("double_contains", [])):
            return None

        # 1) 优先提取引号中的关键词（支持中英文引号）
        quoted = re.findall(r"[“\"‘']([^”\"’']+)[”\"’']", q)
        quoted = [str(x).strip() for x in quoted if str(x).strip()]

        kw1 = ""
        kw2 = ""
        if len(quoted) >= 2:
            kw1, kw2 = quoted[0], quoted[1]
        elif len(quoted) == 1:
            kw1 = quoted[0]
            # 尝试从“kw1 和 <kw2>”结构中抽取第二个关键词（到常见标点为止）
            m = re.search(
                re.escape(kw1) + r".*?(?:和|以及|及|与)\s*([^？\?。；;，,]+)",
                q,
            )
            if m:
                kw2 = str(m.group(1)).strip()
            else:
                # 退化：直接取“和/以及/及/与”后的片段
                m2 = re.search(r"(?:和|以及|及|与)\s*([^？\?。；;，,]+)", q)
                if m2:
                    kw2 = str(m2.group(1)).strip()
        else:
            # 没有引号时，尽量从“同时包含A和B”里抽取
            m = re.search(r"同时包含(?:了)?\s*([^和以及及与]+)\s*(?:和|以及|及|与)\s*([^？\?。；;，,]+)", q)
            if m:
                kw1 = str(m.group(1)).strip()
                kw2 = str(m.group(2)).strip()

        if not kw1 or not kw2:
            return None

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:resultsInFailureEffect]->(fe:FailureEffect)
            WHERE fe.FailureEffect CONTAINS $kw1
              AND fe.FailureEffect CONTAINS $kw2
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY FailureMode
            """.strip(),
            {"kw1": kw1, "kw2": kw2},
        )
        items = [str(r.get("FailureMode") or "").strip() for r in rows]
        items = [x for x in items if x]

        if items:
            answer = f"后果描述同时包含“{kw1}”和“{kw2}”的失效模式包括：" + "，".join(items)
        else:
            answer = f"后果描述中同时包含“{kw1}”和“{kw2}”的失效模式：无。"

        return {
            "answer": answer,
            "context": ["scope=global", f"effect_contains={kw1}&{kw2}", "list=modes"],
            "context_raw": {"kw1": kw1, "kw2": kw2, "modes": items, "count": len(items)},
        }

    def _try_answer_count_modes_by_effect_keyword(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q or "后果" not in q or "总共有多少" not in q or "失效模式" not in q:
            return None
        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None
        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:resultsInFailureEffect]->(fe:FailureEffect)
            WHERE fe.FailureEffect CONTAINS $kw
            RETURN count(DISTINCT fd) AS c
            """.strip(),
            {"kw": kw},
        )
        c = int(rows[0].get("c", 0) or 0) if rows else 0
        answer = f"后果包含“{kw}”的失效模式共有 {c} 项。"
        return {
            "answer": answer,
            "context": ["scope=global", f"effect_kw={kw}", "agg=count"],
            "context_raw": {"keyword": kw, "count": c},
        }

    def _try_answer_projects_by_effect_keyword(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q or "后果为" not in q or "集中" not in q or "设计项目" not in q:
            return None
        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None
        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:resultsInFailureEffect]->(fe:FailureEffect)
            MATCH (fd)-[:occursAtProcessStep]->(ps:ProcessStep)
            WHERE fe.FailureEffect CONTAINS $kw
            RETURN DISTINCT ps.ProcessStep AS ProcessStep
            ORDER BY ProcessStep
            """.strip(),
            {"kw": kw},
        )
        items = [str(r.get("ProcessStep") or "").strip() for r in rows]
        items = [x for x in items if x]
        if not items:
            return None
        answer = f"后果包含“{kw}”的失效模式主要分布在这些设计项目：" + "，".join(items)
        return {
            "answer": answer,
            "context": ["scope=global", f"effect_kw={kw}", "list=projects"],
            "context_raw": items,
        }

