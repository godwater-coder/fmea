# -*- coding: utf-8 -*-

# 该文件负责组装 KGRAGService，并完成服务初始化与 Mixin 组合。

from os import getenv
import collections
import openai
from langchain_openai import OpenAIEmbeddings

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
)


class KGRAGService(
    ServicePipelineMixin,
    ServiceDeterministicMixin,
    ServiceOpsMixin,
    Neo4JRepository,
):
    """KG RAG Service for FMEA."""

    # 选embedding → 初始化Neo4j仓储（父类）→ 设置 RAG 过程要用的参数/上下文。
    def __init__(self):
        # 尝试使用环境变量指定的 embedding 模型，默认降级到低成本模型以避免配额问题
        model_name = getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        try:
            embedding_instance = OpenAIEmbeddings(model=model_name)
        except Exception as e:
            # 兼容 openai v0.x/v1.x：RateLimitError 可能位于不同位置，或根本不存在。
            rate_limit_err = getattr(openai, "RateLimitError", None)
            if rate_limit_err and isinstance(e, rate_limit_err):
                # 如果因为配额问题无法创建，尝试降级为更便宜的模型
                if model_name != "text-embedding-3-small":
                    try:
                        embedding_instance = OpenAIEmbeddings(model="text-embedding-3-small")
                    except Exception as e2:
                        raise RuntimeError(
                            "Embedding 创建失败：可能超出配额或模型不可用。请检查 OpenAI 账单与配额，或设置 OPENAI_EMBEDDING_MODEL 环境变量来使用允许的模型。"
                        ) from e2
                else:
                    raise RuntimeError(
                        "Embedding 创建失败：可能超出配额或模型不可用。请检查 OpenAI 账单与配额，或设置 OPENAI_EMBEDDING_MODEL 环境变量来使用允许的模型。"
                    ) from e
            else:
                # 如果是认证错误或无效 API key，降级为本地 DummyEmbeddings，避免整个服务宕机。
                msg = str(e)
                if (
                    "invalid_api_key" in msg
                    or "Incorrect API key" in msg
                    or "AuthenticationError" in type(e).__name__
                ):
                    class DummyEmbeddings:
                        def __init__(self, dim: int = 3):
                            self.dim = dim

                        def embed_query(self, text: str):
                            return [0.0] * self.dim

                        def embed_documents(self, docs):
                            return [[0.0] * self.dim for _ in docs]

                    embedding_instance = DummyEmbeddings(dim=3)
                else:
                    raise RuntimeError(
                        "Embedding 初始化失败：%s" % str(e)
                    ) from e

        super().__init__(
            url=NEO4J_URL,
            username=NEO4J_USERNAME,
            password=NEO4J_PASSWORD,
            database=NEO4J_DATABASE,
            embedding=embedding_instance,
        )

        # Neo4j 向量索引配置（与 langchain Neo4jVector 保持一致）
        self.vector_index_name = getenv("NEO4J_VECTOR_INDEX_NAME", "vector")
        self.vector_node_label = getenv("NEO4J_VECTOR_NODE_LABEL", "Chunk")
        self.vector_embedding_property = getenv("NEO4J_VECTOR_EMBEDDING_PROPERTY", "embedding")

        self.top_k = 3  # 默认每次最多用 3 条“上下文/证据”来回答问题

        # 给当前服务对象创建一个“消息列表”，专门用于后面让大模型生成 Cypher 查询语句。
        self.context_cypher = [
            dict(
                role="system",
                content=CYPHER_GENERATION_TEMPLATE.format(schema=self.schema),
            )
        ]
        self.context_qa = collections.deque(maxlen=1)
        self._dfmea_cache_path: str | None = None
        self._dfmea_cache_df: object | None = None
        self.use_deterministic_router = (getenv("QA_USE_DETERMINISTIC_ROUTER", "0") or "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self.query_rewrite_count = max(1, int((getenv("QA_QUERY_REWRITE_COUNT", "3") or "3").strip() or "3"))
