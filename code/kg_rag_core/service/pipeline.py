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

        self._ensure_neo4j_available()

        if not self._is_graph_initialized():
            raise RuntimeError(
                "知识图谱尚未初始化：请先调用 /api/v1/create-fmea-graph 将 CSV 导入 Neo4j 并建立向量索引。"
            )

        # === 全局/跨项目 deterministic 分支（客观查表问题尽量避免走 LLM） ===
        direct_top5 = self._try_answer_global_top_rpn_with_project(question)
        if direct_top5 is not None:
            answer_file = self._save_answer_to_file(direct_top5["answer"])
            return {
                "answer": direct_top5["answer"],
                "answer_file": answer_file,
                "context": direct_top5.get("context", []),
                "context_raw": direct_top5.get("context_raw", []),
            }

        direct_thr = self._try_answer_global_rpn_threshold_list(question)
        if direct_thr is not None:
            answer_file = self._save_answer_to_file(direct_thr["answer"])
            return {
                "answer": direct_thr["answer"],
                "answer_file": answer_file,
                "context": direct_thr.get("context", []),
                "context_raw": direct_thr.get("context_raw", []),
            }

        direct_proj_max = self._try_answer_project_max_avg_metric(question)
        if direct_proj_max is not None:
            answer_file = self._save_answer_to_file(direct_proj_max["answer"])
            return {
                "answer": direct_proj_max["answer"],
                "answer_file": answer_file,
                "context": direct_proj_max.get("context", []),
                "context_raw": direct_proj_max.get("context_raw", {}),
            }

        direct_global_extreme_followup = self._try_answer_global_extreme_mode_followup(question)
        if direct_global_extreme_followup is not None:
            answer_file = self._save_answer_to_file(direct_global_extreme_followup["answer"])
            return {
                "answer": direct_global_extreme_followup["answer"],
                "answer_file": answer_file,
                "context": direct_global_extreme_followup.get("context", []),
                "context_raw": direct_global_extreme_followup.get("context_raw", {}),
            }

        direct_global_extreme = self._try_answer_global_extreme_metric_modes(question)
        if direct_global_extreme is not None:
            answer_file = self._save_answer_to_file(direct_global_extreme["answer"])
            return {
                "answer": direct_global_extreme["answer"],
                "answer_file": answer_file,
                "context": direct_global_extreme.get("context", []),
                "context_raw": direct_global_extreme.get("context_raw", {}),
            }

        direct_cmp = self._try_answer_compare_two_projects_avg_rpn(question)
        if direct_cmp is not None:
            answer_file = self._save_answer_to_file(direct_cmp["answer"])
            return {
                "answer": direct_cmp["answer"],
                "answer_file": answer_file,
                "context": direct_cmp.get("context", []),
                "context_raw": direct_cmp.get("context_raw", {}),
            }

        direct_s_eff = self._try_answer_effects_and_modes_by_severity(question)
        if direct_s_eff is not None:
            answer_file = self._save_answer_to_file(direct_s_eff["answer"])
            return {
                "answer": direct_s_eff["answer"],
                "answer_file": answer_file,
                "context": direct_s_eff.get("context", []),
                "context_raw": direct_s_eff.get("context_raw", {}),
            }

        direct_s_modes = self._try_answer_modes_by_severity(question)
        if direct_s_modes is not None:
            answer_file = self._save_answer_to_file(direct_s_modes["answer"])
            return {
                "answer": direct_s_modes["answer"],
                "answer_file": answer_file,
                "context": direct_s_modes.get("context", []),
                "context_raw": direct_s_modes.get("context_raw", {}),
            }

        direct_double_eff = self._try_answer_modes_by_effect_double_contains(question)
        if direct_double_eff is not None:
            answer_file = self._save_answer_to_file(direct_double_eff["answer"])
            return {
                "answer": direct_double_eff["answer"],
                "answer_file": answer_file,
                "context": direct_double_eff.get("context", []),
                "context_raw": direct_double_eff.get("context_raw", {}),
            }

        direct_cnt_eff = self._try_answer_count_modes_by_effect_keyword(question)
        if direct_cnt_eff is not None:
            answer_file = self._save_answer_to_file(direct_cnt_eff["answer"])
            return {
                "answer": direct_cnt_eff["answer"],
                "answer_file": answer_file,
                "context": direct_cnt_eff.get("context", []),
                "context_raw": direct_cnt_eff.get("context_raw", {}),
            }

        direct_proj_eff = self._try_answer_projects_by_effect_keyword(question)
        if direct_proj_eff is not None:
            answer_file = self._save_answer_to_file(direct_proj_eff["answer"])
            return {
                "answer": direct_proj_eff["answer"],
                "answer_file": answer_file,
                "context": direct_proj_eff.get("context", []),
                "context_raw": direct_proj_eff.get("context_raw", []),
            }

        direct_prev_types = self._try_answer_prevent_control_types(question)
        if direct_prev_types is not None:
            answer_file = self._save_answer_to_file(direct_prev_types["answer"])
            return {
                "answer": direct_prev_types["answer"],
                "answer_file": answer_file,
                "context": direct_prev_types.get("context", []),
                "context_raw": direct_prev_types.get("context_raw", []),
            }

        direct_det_types = self._try_answer_detect_control_types(question)
        if direct_det_types is not None:
            answer_file = self._save_answer_to_file(direct_det_types["answer"])
            return {
                "answer": direct_det_types["answer"],
                "answer_file": answer_file,
                "context": direct_det_types.get("context", []),
                "context_raw": direct_det_types.get("context_raw", []),
            }

        direct_det_projects = self._try_answer_projects_by_detection_measure(question)
        if direct_det_projects is not None:
            answer_file = self._save_answer_to_file(direct_det_projects["answer"])
            return {
                "answer": direct_det_projects["answer"],
                "answer_file": answer_file,
                "context": direct_det_projects.get("context", []),
                "context_raw": direct_det_projects.get("context_raw", []),
            }

        direct_ctrl_pref = self._try_answer_control_preference_by_project(question)
        if direct_ctrl_pref is not None:
            answer_file = self._save_answer_to_file(direct_ctrl_pref["answer"])
            return {
                "answer": direct_ctrl_pref["answer"],
                "answer_file": answer_file,
                "context": direct_ctrl_pref.get("context", []),
                "context_raw": direct_ctrl_pref.get("context_raw", []),
            }

        direct_ctrl_presence = self._try_answer_modes_by_control_presence(question)
        if direct_ctrl_presence is not None:
            answer_file = self._save_answer_to_file(direct_ctrl_presence["answer"])
            return {
                "answer": direct_ctrl_presence["answer"],
                "answer_file": answer_file,
                "context": direct_ctrl_presence.get("context", []),
                "context_raw": direct_ctrl_presence.get("context_raw", []),
            }

        direct_ctrl_by_mode = self._try_answer_controls_by_failure_mode(question)
        if direct_ctrl_by_mode is not None:
            answer_file = self._save_answer_to_file(direct_ctrl_by_mode["answer"])
            return {
                "answer": direct_ctrl_by_mode["answer"],
                "answer_file": answer_file,
                "context": direct_ctrl_by_mode.get("context", []),
                "context_raw": direct_ctrl_by_mode.get("context_raw", []),
            }

        direct_ctrl_cat = self._try_answer_control_category_by_keyword(question)
        if direct_ctrl_cat is not None:
            answer_file = self._save_answer_to_file(direct_ctrl_cat["answer"])
            return {
                "answer": direct_ctrl_cat["answer"],
                "answer_file": answer_file,
                "context": direct_ctrl_cat.get("context", []),
                "context_raw": direct_ctrl_cat.get("context_raw", []),
            }

        direct_threats = self._try_answer_threats_by_protection_level(question)
        if direct_threats is not None:
            answer_file = self._save_answer_to_file(direct_threats["answer"])
            return {
                "answer": direct_threats["answer"],
                "answer_file": answer_file,
                "context": direct_threats.get("context", []),
                "context_raw": direct_threats.get("context_raw", []),
            }

        direct_prev_causes = self._try_answer_failure_causes_by_prevent_control(question)
        if direct_prev_causes is not None:
            answer_file = self._save_answer_to_file(direct_prev_causes["answer"])
            return {
                "answer": direct_prev_causes["answer"],
                "answer_file": answer_file,
                "context": direct_prev_causes.get("context", []),
                "context_raw": direct_prev_causes.get("context_raw", []),
            }

        direct_cause_sem = self._try_answer_failure_causes_by_semantic_category(question)
        if direct_cause_sem is not None:
            answer_file = self._save_answer_to_file(direct_cause_sem["answer"])
            return {
                "answer": direct_cause_sem["answer"],
                "answer_file": answer_file,
                "context": direct_cause_sem.get("context", []),
                "context_raw": direct_cause_sem.get("context_raw", []),
            }

        direct_cause_phrase = self._try_answer_modes_by_cause_phrase_quoted(question)
        if direct_cause_phrase is not None:
            answer_file = self._save_answer_to_file(direct_cause_phrase["answer"])
            return {
                "answer": direct_cause_phrase["answer"],
                "answer_file": answer_file,
                "context": direct_cause_phrase.get("context", []),
                "context_raw": direct_cause_phrase.get("context_raw", []),
            }

        direct_cause_kw = self._try_answer_modes_by_cause_keyword(question)
        if direct_cause_kw is not None:
            answer_file = self._save_answer_to_file(direct_cause_kw["answer"])
            return {
                "answer": direct_cause_kw["answer"],
                "answer_file": answer_file,
                "context": direct_cause_kw.get("context", []),
                "context_raw": direct_cause_kw.get("context_raw", []),
            }

        direct_ctrl = self._try_answer_modes_by_control_keyword(question)
        if direct_ctrl is not None:
            answer_file = self._save_answer_to_file(direct_ctrl["answer"])
            return {
                "answer": direct_ctrl["answer"],
                "answer_file": answer_file,
                "context": direct_ctrl.get("context", []),
                "context_raw": direct_ctrl.get("context_raw", []),
            }

        direct_per_mode = self._try_answer_per_mode_metric_by_process_step(question)
        if direct_per_mode is not None:
            answer_file = self._save_answer_to_file(direct_per_mode["answer"])
            return {
                "answer": direct_per_mode["answer"],
                "answer_file": answer_file,
                "context": direct_per_mode.get("context", []),
                "context_raw": direct_per_mode.get("context_raw", []),
            }

        direct_extreme = self._try_answer_extreme_metric_mode_by_process_step(question)
        if direct_extreme is not None:
            answer_file = self._save_answer_to_file(direct_extreme["answer"])
            return {
                "answer": direct_extreme["answer"],
                "answer_file": answer_file,
                "context": direct_extreme.get("context", []),
                "context_raw": direct_extreme.get("context_raw", []),
            }

        direct_list_triplet = self._try_answer_modes_effects_causes_by_process_step(question)
        if direct_list_triplet is not None:
            answer_file = self._save_answer_to_file(direct_list_triplet["answer"])
            return {
                "answer": direct_list_triplet["answer"],
                "answer_file": answer_file,
                "context": direct_list_triplet.get("context", []),
                "context_raw": direct_list_triplet.get("context_raw", []),
            }

        direct_avg = self._try_answer_avg_metric_by_process_step(question)
        if direct_avg is not None:
            answer_file = self._save_answer_to_file(direct_avg["answer"])
            return {
                "answer": direct_avg["answer"],
                "answer_file": answer_file,
                "context": direct_avg.get("context", []),
                "context_raw": direct_avg.get("context_raw", []),
            }

        direct = self._try_answer_failure_modes_by_process_step(question)
        if direct is not None:
            answer_file = self._save_answer_to_file(direct["answer"])
            return {
                "answer": direct["answer"],
                "answer_file": answer_file,
                "context": direct.get("context", []),
                "context_raw": direct.get("context_raw", []),
            }

        # 统一进入“问题预处理 + 图检索/向量检索 + 生成回答”流程
        prep = self._preprocess_question_for_retrieval(question)
        return self._answer_question_via_vector_rag(prep)

# ------------------------------------------------------------------------------------------------------------------
