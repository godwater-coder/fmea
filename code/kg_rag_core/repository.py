# -*- coding: utf-8 -*-

# 该文件实现 Neo4j 仓储层，封装图查询与向量检索基础能力。

from os import getenv
from langchain_community.vectorstores import Neo4jVector
from langchain_community.graphs import Neo4jGraph
from langchain_openai import OpenAIEmbeddings


class Neo4JRepository(Neo4jVector, Neo4jGraph):
    # 把“Neo4j 图能力 + Neo4j 向量检索能力”封装成一个更稳健的仓储层，
    # 并且在 embedding / 网络 / 多继承初始化不稳定时做降级，避免整个服务直接启动失败。
    """Neo4J Repository."""

    def __init__(
        self,
        url: str,# str是给类型检查工具看的，类型标注
        username: str,
        password: str,
        database: str,
        embedding: OpenAIEmbeddings,
    ) -> None: #返回值类型标注，返回NONE
        # 在把 embedding 传给父类之前，先尝试本地探测 embedding 是否可用。
        # 这样可以在 API key 无效或网络不可达时，替换为 DummyEmbeddings，
        # 避免第三方库在其 __init__ 中直接调用网络导致未捕获异常。

        class DummyEmbeddings: # 当embedding不可用时的降级实现
            def __init__(self, dim: int = 3):
                self.dim = dim

            def embed_query(self, text: str):
                return [0.0] * self.dim # 返回固定长度全为0的向量

            def embed_documents(self, docs):
                return [[0.0] * self.dim for _ in docs] # 给每个文档返回一个全 0 向量

        try:
            # 轻量探测：调用一次 embed_query，若成功则继续使用传入 embedding
            _ = embedding.embed_query("foo")
        except Exception:
            # 若探测失败，替换为 DummyEmbeddings，避免父类初始化时触发网络调用错误
            embedding = DummyEmbeddings(dim=3)

        # 现在安全地调用父类初始化
        super().__init__(
            url=url,
            username=username,
            password=password,
            database=database,
            embedding=embedding,
            index_name=getenv("NEO4J_VECTOR_INDEX_NAME", "vector"),
        )

        try:
            # 显式初始化图相关基类，防止多继承顺序导致未初始化的属性
            Neo4jGraph.__init__(self, url=url, username=username, password=password, database=database)
        except Exception:
            # 如果显式初始化失败，也设置一个安全的默认属性以避免 AttributeError
            if not hasattr(self, "_enhanced_schema"):
                self._enhanced_schema = {}
            if not hasattr(self, "_enhanced_schema_cypher"):
                self._enhanced_schema_cypher = None

        # 确保即便父类未按预期设置这些内部属性，仍然有安全默认值，
        # 然后刷新 schema（现在相关内部属性应该已存在）
        if not hasattr(self, "_enhanced_schema"):
            self._enhanced_schema = {}
        if not hasattr(self, "_enhanced_schema_cypher"):
            self._enhanced_schema_cypher = None

        try:
            self.refresh_schema()
        except Exception:
            # 刷新失败时降级为安全行为，不抛出致命错误
            pass

# ------------------------------------------------------------------------------------------------------------------

