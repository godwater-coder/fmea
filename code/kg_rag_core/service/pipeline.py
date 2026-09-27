# -*- coding: utf-8 -*-

# 该文件负责问答主流程编排（pipeline），组织规则分支、检索与最终回答生成。

class ServicePipelineMixin:
    def answer_question(self, question: str) -> dict:
        """
        Run answer question RAG service.

        Args:
            question (str): The question to answer.

        Returns:
            dict: The answer and context.
        """
        if not question or not str(question).strip():
            raise ValueError("question 不能为空")

        if (
            getattr(self, "route_mode", "evidence") != "fixed"
            and getattr(self, "enable_semantic_priority", True)
            and getattr(self, "enable_query_ir", True)
            and getattr(self, "enable_semantic_retrieval_enhancement", True)
            and self._should_prioritize_semantic_rag(question)
        ):
            try:
                self._ensure_neo4j_available()
                graph_ready_for_rag = self._is_graph_initialized()
            except Exception:
                graph_ready_for_rag = False
            if graph_ready_for_rag:
                prep = self._preprocess_question_for_retrieval(question)
                prep["allow_llm_cypher"] = False
                prep["summarize_chunks"] = False
                prep["route"] = "semantic_rag"
                result = self._answer_question_via_vector_rag(prep)
                has_evidence = bool(result.get("context_raw") or result.get("context"))
                result["adjudication"] = {
                    "status": "answered" if has_evidence else "rejected",
                    "reason": "semantic_evidence_confirmed" if has_evidence else "no_evidence",
                    "route": "semantic_rag",
                    "conflicts": [],
                    "missing_slots": [],
                }
                return result
        
        # 1.尝试 CSV 直答规则。消融实验 M1 会关闭该分支。
        if getattr(self, "enable_csv_basic", True):
            basic_csv = self._try_answer_basic_csv_lookup(question)
            if basic_csv is not None:
                basic_csv = self._normalize_evidence_payload(basic_csv, question)
                answer_file = self._save_answer_to_file(basic_csv["answer"])
                return {
                    "answer": basic_csv["answer"],
                    "answer_file": answer_file,
                    "context": basic_csv.get("context", []),
                    "context_raw": basic_csv.get("context_raw", []),
                    "route": "csv_basic",
                    "route_confidence": 1.0,
                    "missing_slots": [],
                    "adjudication": {
                        "status": "answered",
                        "reason": "csv_evidence_confirmed",
                        "route": "csv_basic",
                        "conflicts": [],
                        "missing_slots": [],
                    },
                }

        try:
            self._ensure_neo4j_available()
            graph_ready = self._is_graph_initialized()
        except Exception:
            graph_ready = False

        def _finalize_direct_answer(payload: dict[str, object]) -> dict[str, object]:
            payload = self._normalize_evidence_payload(payload, question)
            answer_text = str(payload.get("answer") or "")
            answer_file = self._save_answer_to_file(answer_text)
            result = dict(payload)
            result["answer"] = answer_text
            result["answer_file"] = answer_file
            result.setdefault("route", "deterministic_rule")
            result.setdefault("route_confidence", 1.0)
            result.setdefault("adjudication", {
                "status": "answered",
                "reason": "deterministic_evidence_confirmed",
                "route": str(result.get("route") or "deterministic_rule"),
                "conflicts": [],
                "missing_slots": [],
            })
            return result

        # 2. deterministic 规则问答。先让这些显式规则吃掉结构清晰的问题，
        # 再把剩余问题交给 Query IR / 向量 RAG。
        direct_checks = (
            self._try_answer_structured_clue_rule,
            self._try_answer_global_top_rpn_with_project,
            self._try_answer_global_rpn_threshold_list,
            self._try_answer_project_max_avg_metric,
            self._try_answer_global_extreme_mode_followup,
            self._try_answer_global_extreme_metric_modes,
            self._try_answer_compare_two_projects_avg_rpn,
            self._try_answer_effects_and_modes_by_severity,
            self._try_answer_modes_by_severity,
            self._try_answer_modes_by_effect_double_contains,
            self._try_answer_count_modes_by_effect_keyword,
            self._try_answer_projects_by_effect_keyword,
            self._try_answer_prevent_control_types,
            self._try_answer_detect_control_types,
            self._try_answer_projects_by_detection_measure,
            self._try_answer_control_preference_by_project,
            self._try_answer_modes_by_control_presence,
            self._try_answer_cause_by_failure_mode,
            self._try_answer_controls_by_failure_mode,
            self._try_answer_control_category_by_keyword,
            self._try_answer_threats_by_protection_level,
            self._try_answer_failure_causes_by_prevent_control,
            self._try_answer_failure_causes_by_semantic_category,
            self._try_answer_modes_by_cause_phrase_quoted,
            self._try_answer_modes_by_cause_keyword,
            self._try_answer_modes_by_control_keyword,
            self._try_answer_per_mode_metric_by_process_step,
            self._try_answer_extreme_metric_mode_by_process_step,
            self._try_answer_modes_effects_causes_by_process_step,
            self._try_answer_avg_metric_by_process_step,
            self._try_answer_failure_modes_by_process_step,
        )
        for direct_fn in direct_checks:
            direct = direct_fn(question)
            if direct is not None:
                return _finalize_direct_answer(direct)

        if not graph_ready:
            raise RuntimeError(
                "知识图谱尚未初始化，且当前问题未命中 CSV/确定性直答规则。"
                "如需继续，请先调用 /api/v1/create-fmea-graph 导入 CSV，"
                "或设置 DEFAULT_DFMEA_CSV/FMEA_DEFAULT_CSV 让服务可直接查表。"
            )
        
        # 3. Query IR 结构化查询
        # 解析出问题的查询意图 + 根据查询意图在KG中查对应图谱位置 + 检查查询结果是否合理并用LLM生成答案
        # Query IR 的优势是更可解释、更稳定，也更适合 FMEA 这类结构化数据。
        # 它能明确知道用户问的是 RPN、严重度 S、失效原因、探测措施，而不是只靠语义相似度去猜
        if getattr(self, "enable_query_ir", True):
            ir = self.build_query_ir(question)
            execution_result = self.execute_query_ir(ir)
            return self.compose_answer_from_ir(ir, execution_result)

        # 4. 向量RAG
        prep = self._preprocess_question_for_retrieval(question)
        result = self._answer_question_via_vector_rag(prep)
        has_evidence = bool(result.get("context_raw") or result.get("context"))
        result["adjudication"] = {
            "status": "answered" if has_evidence else "rejected",
            "reason": "semantic_evidence_confirmed" if has_evidence else "no_evidence",
            "route": "semantic_rag",
            "conflicts": [],
            "missing_slots": [],
        }
        return result

# ------------------------------------------------------------------------------------------------------------------
