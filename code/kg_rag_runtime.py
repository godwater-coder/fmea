# -*- coding: utf-8 -*-

from __future__ import annotations

import threading
from os import getenv
from urllib.parse import urlparse

from kg_rag_core import KGRAGService

# RAG 服务（懒初始化）
#先不创建KGRAGServace，等第一次有人调用接口时在创建
# 原因：`Neo4jVector.__init__` 会立即 `verify_connectivity()`。
# 当 NEO4J_URL 指向 Aura 但当前机器无法解析外网域名/无网络时，
# 若在模块加载阶段就初始化，会导致 `python code/kg_rag.py` 直接崩溃、服务无法启动。

_rag_service = None #已经创建好的服务实例
_rag_service_init_error: Exception | None = None #上次初始化失败记录的异常
_rag_service_lock = threading.Lock() #并发初始化时用到的锁

#从Neo4j的URL中解析出host和post
def _neo4j_url_host_port(url: str | None) -> tuple[str | None , int | None]:
    if not url:
        return None, None
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port
        return host, port
    except Exception:
        return None, None


def _format_neo4j_init_error(e: Exception) -> str:
    # 让启动/接口报错更可读，并给出可执行的配置建议。
    neo4j_url = getenv("NEO4J_URL")
    host, port = _neo4j_url_host_port(neo4j_url)

    base = f"Neo4j 连接初始化失败：{e}"
    tips: list[str] = []

    if not neo4j_url:
        tips.append("未设置环境变量 NEO4J_URL（请在 .env 中配置）。")
    else:
        tips.append(f"当前 NEO4J_URL={neo4j_url}")

    # 常见：Aura 域名解析失败
    msg = str(e)
    if "Cannot resolve address" in msg or "gaierror" in msg or "Name or service not known" in msg:
        if host:
            tips.append(f"DNS 无法解析主机：{host}{(':' + str(port)) if port else ''}")
        tips.append("请检查：VM 是否有网络/DNS（能否解析外网域名）。")
        tips.append("若你要连接本地 Neo4j：把 NEO4J_URL 改为 bolt://localhost:7687（或你的实际地址）。")
        tips.append("若你要连接 Aura：确保机器能访问外网并能解析 *.databases.neo4j.io。")
    else:
        tips.append("请检查 NEO4J_USERNAME/NEO4J_PASSWORD/NEO4J_DATABASE 是否与 Neo4j 实例一致。")

    return base + "\n" + "\n".join(tips)


def get_rag_service() -> KGRAGService:
    global _rag_service, _rag_service_init_error
    if _rag_service is not None:
        return _rag_service

    with _rag_service_lock:
        if _rag_service is not None:
            return _rag_service
        if _rag_service_init_error is not None:
            raise RuntimeError(_format_neo4j_init_error(_rag_service_init_error))
        try:
            _rag_service = KGRAGService()
            return _rag_service
        except Exception as e:
            _rag_service_init_error = e
            raise RuntimeError(_format_neo4j_init_error(e))
