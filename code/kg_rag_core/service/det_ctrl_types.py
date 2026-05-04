# -*- coding: utf-8 -*-

# 该文件承载控制措施类型归纳（预防/探测）及“措施对应项目”相关问答分支。

import re


class DeterministicControlsTypesMixin:
    def _try_answer_prevent_control_types(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "现行预防性" not in q or "设计控制" not in q:
            return None
        if not ("有哪些类型" in q or "主要有哪些类型" in q):
            return None

        # 优先使用新图结构：FailureMode 上的专用字段
        rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.PreventControl IS NOT NULL AND trim(toString(fd.PreventControl)) <> ''
            RETURN DISTINCT toString(fd.PreventControl) AS v
            """.strip(),
            {},
        )
        items = [str(r.get("v") or "").strip() for r in rows]
        items = [x for x in items if x and x.lower() != "nan"]

        # 回退兼容：解析旧图中的 FailureMeasure 混合文本
        if not items:
            rows = self._query_params(
                """
                MATCH (fm:FailureMeasure)
                WHERE fm.FailureMeasure IS NOT NULL AND toString(fm.FailureMeasure) CONTAINS '预防控制：'
                RETURN DISTINCT toString(fm.FailureMeasure) AS v
                """.strip(),
                {},
            )
            blob = [str(r.get("v") or "").strip() for r in rows]
            blob = [b for b in blob if b]
            extracted: list[str] = []
            for b in blob:
                m = re.search(r"预防控制：([^；]+)", b)
                if m:
                    extracted.append(m.group(1).strip())
            items = [x for x in extracted if x]

        if not items:
            return None

        # 分组并给出示例
        cats: list[tuple[str, list[str]]] = []

        def _pick_examples(pred, limit=3):
            ex = [x for x in items if pred(x)]
            # 保持稳定顺序
            seen = set()
            out = []
            for x in ex:
                if x not in seen:
                    seen.add(x)
                    out.append(x)
                if len(out) >= limit:
                    break
            return out

        examples_protect = _pick_examples(lambda x: "防护" in x or "IP" in x)
        if examples_protect:
            cats.append(("提高防护等级/防护设计", examples_protect))

        examples_std = _pick_examples(lambda x: "标准" in x)
        if examples_std:
            cats.append(("设定标准/阈值", examples_std))

        examples_upgrade = _pick_examples(lambda x: "升级" in x or "算法" in x or "SOC" in x or "BMS" in x)
        if examples_upgrade:
            cats.append(("系统/软件升级与算法优化", examples_upgrade))

        examples_mark = _pick_examples(lambda x: "颜色" in x or "材料" in x or "区分" in x)
        if examples_mark:
            cats.append(("标识与材料区分", examples_mark))

        # 其他分组
        used = set(sum((ex for _, ex in cats), []))
        others = [x for x in items if x not in used]
        if others:
            cats.append(("其他", others[:3]))

        parts = []
        for name, ex in cats:
            if ex:
                parts.append(f"{name}（例如：" + "、".join(ex) + "）")
            else:
                parts.append(name)

        answer = "文档中提到的现行预防性设计控制主要类型包括：" + "；".join(parts) + "。"
        return {
            "answer": answer,
            "context": ["scope=global", "control=prevent", "type_summary"],
            "context_raw": {"items": items, "categories": cats},
        }

    def _try_answer_detect_control_types(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "现行探测性" not in q or "设计控制" not in q:
            return None
        if not ("有哪些类型" in q or "主要有哪些类型" in q):
            return None

        # 优先使用新图结构：FailureMode 上的专用字段
        rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.DetectionMeasure IS NOT NULL AND trim(toString(fd.DetectionMeasure)) <> ''
            RETURN DISTINCT toString(fd.DetectionMeasure) AS v
            """.strip(),
            {},
        )
        items = [str(r.get("v") or "").strip() for r in rows]
        items = [x for x in items if x and x.lower() != "nan"]

        # 回退兼容：使用 FailureMeasure 节点上的 DetectionMeasure
        if not items:
            rows = self._query_params(
                """
                MATCH (fm:FailureMeasure)
                WHERE fm.DetectionMeasure IS NOT NULL AND trim(toString(fm.DetectionMeasure)) <> ''
                RETURN DISTINCT toString(fm.DetectionMeasure) AS v
                """.strip(),
                {},
            )
            items = [str(r.get("v") or "").strip() for r in rows]
            items = [x for x in items if x and x.lower() != "nan"]

        if not items:
            return None

        def _uniq_keep_order(xs: list[str]) -> list[str]:
            seen = set()
            out = []
            for x in xs:
                if x not in seen:
                    seen.add(x)
                    out.append(x)
            return out

        items = _uniq_keep_order(items)

        # 按问句期望分组：测试/检查/测量/试验/检测/保护
        def _ex(pred, limit=4):
            return [x for x in items if pred(x)][:limit]

        groups: list[tuple[str, list[str]]] = []

        ex_test = _ex(lambda x: "测试" in x)
        if ex_test:
            groups.append(("测试", ex_test))

        ex_detect = _ex(lambda x: "检测" in x or "绝缘" in x or "漏电" in x)
        if ex_detect:
            groups.append(("检测", ex_detect))

        ex_measure = _ex(lambda x: "测量" in x or "万用表" in x)
        if ex_measure:
            groups.append(("测量", ex_measure))

        ex_trial = _ex(lambda x: "试验" in x or "挤压" in x or "震动" in x or "老化" in x or "阻燃" in x)
        if ex_trial:
            groups.append(("试验/验证", ex_trial))

        ex_check = _ex(lambda x: "检查" in x or "目视" in x)
        if ex_check:
            groups.append(("检查", ex_check))

        ex_protect = _ex(lambda x: "保护" in x or "报警" in x)
        if ex_protect:
            groups.append(("保护/监测", ex_protect))

        used = set(sum((ex for _, ex in groups), []))
        others = [x for x in items if x not in used]
        if others:
            groups.append(("其他", others[:4]))

        parts = []
        for name, ex in groups:
            if ex:
                parts.append(f"{name}（例如：" + "、".join(ex) + "）")
            else:
                parts.append(name)
        answer = "文档中提到的现行探测性设计控制主要类型包括：" + "；".join(parts) + "。"
        return {
            "answer": answer,
            "context": ["scope=global", "control=detect", "type_summary"],
            "context_raw": {"items": items, "groups": groups},
        }

    def _try_answer_projects_by_detection_measure(self, question: str) -> dict | None:
        """确定性回答：“X”主要应用于哪些设计项目（X 为探测控制）。

        原因：这是纯查表问题，若交给 LLM 容易过度泛化并返回无关项目。
        """

        q = (question or "").strip()
        if not q:
            return None
        if "主要应用于" not in q:
            return None
        if "设计项目" not in q and "项目" not in q:
            return None
        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None

        rows = self._query_params(
            """
            MATCH (ps:ProcessStep)<-[:occursAtProcessStep]-(fd:FailureMode)
            WHERE (
                fd.DetectionMeasure IS NOT NULL AND trim(toString(fd.DetectionMeasure)) <> ''
                AND toString(fd.DetectionMeasure) CONTAINS $kw
            ) OR EXISTS {
                MATCH (fd)-[:isDueToFailureCause]->(:FailureCause)-[:isImprovedByFailureMeasure]->(fm:FailureMeasure)
                WHERE fm.DetectionMeasure IS NOT NULL AND trim(toString(fm.DetectionMeasure)) <> ''
                  AND toString(fm.DetectionMeasure) CONTAINS $kw
            }
            RETURN DISTINCT ps.ProcessStep AS ProcessStep
            ORDER BY ProcessStep
            """.strip(),
            {"kw": kw},
        )
        items = [str(r.get("ProcessStep") or "").strip() for r in rows]
        items = [x for x in items if x]
        if not items:
            return None

        if len(items) == 1:
            answer = f"{kw} 主要应用于：{items[0]}。"
        else:
            answer = f"{kw} 主要应用于以下设计项目：" + "，".join(items) + "。"

        return {
            "answer": answer,
            "context": ["scope=global", f"detect_kw={kw}", "list=projects"],
            "context_raw": items,
        }

