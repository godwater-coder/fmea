import sys
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace
import types


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = PROJECT_ROOT / "code"
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

fake_langchain_community = types.ModuleType("langchain_community")
fake_vectorstores = types.ModuleType("langchain_community.vectorstores")
fake_graphs = types.ModuleType("langchain_community.graphs")


class _FakeNeo4jVector:
    pass


class _FakeNeo4jGraph:
    pass


fake_vectorstores.Neo4jVector = _FakeNeo4jVector
fake_graphs.Neo4jGraph = _FakeNeo4jGraph
fake_langchain_community.vectorstores = fake_vectorstores
fake_langchain_community.graphs = fake_graphs
sys.modules.setdefault("langchain_community", fake_langchain_community)
sys.modules.setdefault("langchain_community.vectorstores", fake_vectorstores)
sys.modules.setdefault("langchain_community.graphs", fake_graphs)

from kg_rag_core.query_ir import QueryEntity, QueryIR  # noqa: E402
from kg_rag_core.service.ops import ServiceOpsMixin  # noqa: E402


class StubService(ServiceOpsMixin):
    def __init__(self):
        self.top_k = 3
        self.context_qa = deque(maxlen=1)
        self.saved_answers = []

    def _save_answer_to_file(self, answer_text: str) -> str:
        self.saved_answers.append(answer_text)
        return "/tmp/fake-answer.txt"

    def run_inference(self, context, temperature=0.0, max_tokens=4000):
        content = "候选证据摘要"
        if context and isinstance(context[0], dict):
            content = str(context[0].get("content") or content)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    def summarize_context(self, context: str, question: str) -> dict:
        return {"role": "system", "content": f"summary:{question}:{context}"}

    def qa_prompt_context(self, question: str, answer_context: str):
        self.context_qa.clear()
        self.context_qa.append({"role": "user", "content": f"{question}\n{answer_context}"})

    def _ensure_vector_index(self) -> None:
        return None

    def _vector_search_multi_queries(self, queries: list[str], k: int) -> list[str]:
        return ["chunk-a", "chunk-b"]


class BooleanRelationStubService(StubService):
    def _match_failure_mode_name(self, mode_key: str) -> str | None:
        return mode_key

    def _query_params(self, cypher: str, params: dict) -> list[dict]:
        if "resultsInFailureEffect" in cypher:
            return [{"value": "影响用户使用"}]
        if "isDueToFailureCause" in cypher:
            return [{"value": "单节电池容量降低或损坏"}]
        return []


class EvidenceAdjudicationTests(unittest.TestCase):
    def setUp(self):
        self.service = StubService()

    def test_structured_evidence_answers_directly(self):
        ir = QueryIR(
            original_question="失效模式“密封失效”的RPN是多少？",
            normalized_question="失效模式“密封失效”的RPN是多少？",
            intent="lookup_metric",
            entities=[QueryEntity(kind="failure_mode", value="密封失效", normalized="密封失效")],
            metric="RPN",
        )
        result = self.service.compose_answer_from_ir(
            ir,
            {
                "route": "structured",
                "answer_hint": "失效模式“密封失效”的RPN是120。",
                "evidence": ["FailureMode=密封失效", "metric=RPN"],
                "context_raw": [{"FailureMode": "密封失效", "RPN": 120}],
                "confidence": 1.0,
                "missing_slots": [],
            },
        )

        self.assertEqual(result["answer"], "失效模式“密封失效”的RPN是120。")
        self.assertEqual(result["adjudication"]["status"], "answered")
        self.assertEqual(result["route"], "structured")

    def test_graph_conflict_rejects_answer(self):
        ir = QueryIR(
            original_question="失效模式“密封失效”的RPN是多少？",
            normalized_question="失效模式“密封失效”的RPN是多少？",
            intent="lookup_metric",
            entities=[QueryEntity(kind="failure_mode", value="密封失效", normalized="密封失效")],
            metric="RPN",
        )
        result = self.service.compose_answer_from_ir(
            ir,
            {
                "route": "graph",
                "evidence": [],
                "context_raw": [
                    {"FailureMode": "密封失效", "value": 120},
                    {"FailureMode": "密封失效", "value": 150},
                ],
                "confidence": 0.8,
                "missing_slots": [],
            },
        )

        self.assertIn("证据存在冲突", result["answer"])
        self.assertEqual(result["adjudication"]["status"], "reject")
        self.assertTrue(result["evidence_conflicts"])

    def test_vector_route_returns_pending_confirmation(self):
        ir = QueryIR(
            original_question="这个项目有哪些风险点？",
            normalized_question="这个项目有哪些风险点？",
            intent="semantic_search",
        )
        ir.query_variants = ["这个项目有哪些风险点？"]
        result = self.service.compose_answer_from_ir(
            ir,
            {
                "route": "vector",
                "evidence": [],
                "context_raw": [],
                "confidence": 0.5,
                "missing_slots": [],
            },
        )

        self.assertIn("待确认", result["answer"])
        self.assertIn("仅命中文本候选证据", result["answer"])
        self.assertEqual(result["adjudication"]["reason"], "vector_candidate_only")
        self.assertEqual(result["route"], "vector")

    def test_boolean_effect_verification_uses_structured_route(self):
        service = BooleanRelationStubService()
        ir = QueryIR(
            original_question="失效模式“巡航里程低于额定值”的后果是否为“影响用户使用”？",
            normalized_question="失效模式“巡航里程低于额定值”的后果是否为“影响用户使用”？",
            intent="boolean_verification",
            entities=[
                QueryEntity(kind="failure_mode", value="巡航里程低于额定值", normalized="巡航里程低于额定值"),
                QueryEntity(kind="effect", value="影响用户使用", normalized="影响用户使用"),
            ],
            output_type="boolean",
        )
        result = service.execute_query_ir(ir)
        self.assertEqual(result["route"], "structured")
        self.assertIn("是。", result["answer_hint"])


if __name__ == "__main__":
    unittest.main()
