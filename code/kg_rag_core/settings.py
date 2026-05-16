# -*- coding: utf-8 -*-

# 该文件集中管理环境变量读取、Ollama 配置以及提示词模板常量。

from os import getenv
import os
from dotenv import load_dotenv


# 加载环境变量
load_dotenv()

# 从环境变量中读取密钥
OLLAMA_BASE_URL = getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_API_BASE = getenv("OLLAMA_API_BASE") or f"{OLLAMA_BASE_URL.rstrip('/')}/v1"
OLLAMA_MODEL = getenv("OLLAMA_MODEL", "qwen3.6:27b")
OLLAMA_EMBEDDING_MODEL = getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_API_KEY = getenv("OLLAMA_API_KEY") or "ollama"
NEO4J_URL = getenv("NEO4J_URL")
NEO4J_USERNAME = getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = getenv("NEO4J_DATABASE")

# 推理模板常量
CYPHER_GENERATION_TEMPLATE = """
说明：
你是一个 Cypher 语句生成器。

硬性约束：
1) 只能使用下方 Schema 中提供的节点标签、关系类型与属性。
2) 不要使用任何 Schema 未提供的关系类型或属性。
3) 如果问题中提到的关系类型不在 Schema 中，但与 Schema 里的某个关系类型语义相近，请选择最相近的那个。

任务：
根据问题生成一条用于查询图数据库的 Cypher 语句。

Schema：
{schema}

输出要求：
- 严禁解释、道歉、对话、Markdown 标记或任何多余文本。
- 只输出 Cypher 语句本身。
- 即使不确定，也必须返回一条 Cypher 语句。
"""

CYPHER_QUESTION_TEMPLATE = """
任务：
生成一条用于查询图数据库的 Cypher 语句。

问题：
{question}
"""

CYPHER_QA_TEMPLATE = """
任务：
你需要基于给定的上下文（JSON 数据结构）回答问题，回答要清晰、对人类友好且可理解。

规则：
1) 上下文是权威的，你不得质疑、推翻或尝试纠正上下文内容。
2) 回答要像自然对话中的直接回答，不要提及“根据上下文/根据 JSON/根据结果”等措辞。
3) 如果上下文为空，请明确回答你不知道。
4) 请用中文回答。

上下文：
"{context}"

问题：
{question} 
"""

ANSWER_SUMMARIZE_TEMPLATE = """
任务：
请对给定信息进行总结，使总结内容能够回答问题，并且适合在后续推理任务中继续使用。

要求：
1) 只保留与问题直接相关的信息，去掉冗余内容。
2) 输出为中文。

信息：
"{information}"

问题：
"{question}"
"""
