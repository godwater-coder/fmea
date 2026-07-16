# -*- coding: utf-8 -*-

from os import getenv
import collections
from types import SimpleNamespace
import requests

from ..repository import Neo4JRepository
from .ops import ServiceOpsMixin
from .det_router import ServiceDeterministicMixin
from .pipeline import ServicePipelineMixin
from ..settings import (
    NEO4J_URL,
    NEO4J_USERNAME,
    NEO4J_PASSWORD,
    NEO4J_DATABASE,
    CYPHER_GENERATION_TEMPLATE,
    QA_ENABLE_QUERY_IR,
    QA_QUERY_IR_STRICT_MODE,
    QA_ENABLE_LLM_CYPHER_FALLBACK,
)


class KGRAGService(
    ServicePipelineMixin,
    ServiceDeterministicMixin,
    ServiceOpsMixin,
    Neo4JRepository,
):
    """KG RAG Service for FMEA."""

    class _OllamaEmbeddings:
        def __init__(self, model: str, base_url: str):
            self.model = model
            self.base_url = base_url.rstrip("/")

        def _embed(self, text: str) -> list[float]:
            resp = requests.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": text},
                timeout=120,
            )
            resp.raise_for_status()
            payload = resp.json()
            vectors = payload.get("embeddings")
            if isinstance(vectors, list) and vectors and isinstance(vectors[0], list):
                return [float(x) for x in vectors[0]]
            embedding = payload.get("embedding")
            if isinstance(embedding, list) and embedding:
                return [float(x) for x in embedding]
            raise RuntimeError(f"Ollama embedding 返回异常：{payload}")

        def embed_query(self, text: str):
            return self._embed(text)

        def embed_documents(self, docs):
            return [self._embed(doc) for doc in docs]

    @staticmethod
    def _ollama_chat(model: str, base_url: str, messages: list[dict], temperature: float = 0.0, max_tokens: int = 4000):
        resp = requests.post(
            f"{base_url.rstrip('/')}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
            timeout=600,
        )
        resp.raise_for_status()
        payload = resp.json()
        content = (
            payload.get("message", {}) if isinstance(payload.get("message"), dict) else {}
        ).get("content", "")
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content)
                )
            ]
        )

    def __init__(self):
        self._degraded_init_error: str | None = None
        self._neo4j_disabled = False
        self._embedding_disabled = False
        self._driver = None
        self.graph = None
        self.schema = ""

        model_name = getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
        base_url = getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"
        try:
            embedding_instance = self._OllamaEmbeddings(model=model_name, base_url=base_url)
            _ = embedding_instance.embed_query("dimension_probe")
        except Exception as e:
            embedding_instance = None
            self._embedding_disabled = True
            self._neo4j_disabled = True
            self._degraded_init_error = (
                "Embedding 初始化失败：请确认 Ollama 已启动、"
                f"OLLAMA_EMBEDDING_MODEL={model_name} 已可用、"
                f"OLLAMA_API_BASE/OLLAMA_BASE_URL 指向正确。原始错误：{e}"
            )

        if embedding_instance is not None:
            try:
                super().__init__(
                    url=NEO4J_URL,
                    username=NEO4J_USERNAME,
                    password=NEO4J_PASSWORD,
                    database=NEO4J_DATABASE,
                    embedding=embedding_instance,
                )
            except Exception as e:
                self._neo4j_disabled = True
                self._degraded_init_error = f"Neo4j 初始化失败：{e}"

        self.vector_index_name = getenv("NEO4J_VECTOR_INDEX_NAME", "vector")
        self.vector_node_label = getenv("NEO4J_VECTOR_NODE_LABEL", "Chunk")
        self.vector_embedding_property = getenv("NEO4J_VECTOR_EMBEDDING_PROPERTY", "embedding")

        self.top_k = 3
        self.context_cypher = [
            dict(role="system", content=CYPHER_GENERATION_TEMPLATE.format(schema=self.schema))
        ]
        self.context_qa = collections.deque(maxlen=1)
        self._dfmea_cache_path: str | None = None
        self._dfmea_cache_df: object | None = None
        self.enable_query_ir = str(QA_ENABLE_QUERY_IR or "1").strip().lower() in {"1", "true", "yes", "on"}
        self.query_ir_strict_mode = str(QA_QUERY_IR_STRICT_MODE or "1").strip().lower() in {"1", "true", "yes", "on"}
        self.enable_llm_cypher_fallback = str(QA_ENABLE_LLM_CYPHER_FALLBACK or "1").strip().lower() in {"1", "true", "yes", "on"}
        self.use_deterministic_router = (getenv("QA_USE_DETERMINISTIC_ROUTER", "0") or "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.query_rewrite_count = max(1, int((getenv("QA_QUERY_REWRITE_COUNT", "3") or "3").strip() or 3))
