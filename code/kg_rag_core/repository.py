# -*- coding: utf-8 -*-

# 该文件实现 Neo4j 仓储层，封装图查询与向量检索基础能力。

from typing import Any
from langchain_community.vectorstores import Neo4jVector
from langchain_community.graphs import Neo4jGraph


class Neo4JRepository(Neo4jVector, Neo4jGraph):
    # 把“Neo4j 图能力 + Neo4j 向量检索能力”封装成一个更稳健的仓储层，
    # 并且在 embedding 初始化失败时直接暴露错误，避免悄悄退化成错误维度向量。
    """Neo4J Repository."""

    def __init__(
        self,
        url: str,# str是给类型检查工具看的，类型标注
        username: str,
        password: str,
        database: str,
        embedding: Any,
    ) -> None: #返回值类型标注，返回NONE
        # 在把 embedding 传给父类之前，先探测一次可用性。
        # 如果这里失败，说明 Ollama embedding 配置本身有问题，不能继续用错误维度继续跑。
        _ = embedding.embed_query("foo")

        # 现在安全地调用父类初始化
        super().__init__(
            url=url,
            username=username,
            password=password,
            database=database,
            embedding=embedding,
            index_name="vector",
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

    def get_embedding_dimension(self) -> int | None:
        try:
            emb = getattr(self, "embedding", None)
            if emb is None:
                return None
            dim = len(emb.embed_query("dimension_probe"))
            return int(dim)
        except Exception:
            return None

# ------------------------------------------------------------------------------------------------------------------
