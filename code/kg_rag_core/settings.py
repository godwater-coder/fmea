# -*- coding: utf-8 -*-

# 该文件集中管理环境变量读取、OpenAI 配置以及提示词模板常量。

from os import getenv, environ
import openai
import os
from dotenv import load_dotenv


# 加载环境变量
load_dotenv()

# 从环境变量中读取密钥
API_KEY = getenv("OPENAI_API_KEY")
NEO4J_URL = getenv("NEO4J_URL")
NEO4J_USERNAME = getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = getenv("NEO4J_DATABASE")

# OpenAI 接口基地址：
# - 官方 OpenAI 默认地址：https://api.openai.com/v1
# - 镜像/代理服务可在 .env 设置 OPENAI_BASE_URL 或 OPENAI_API_BASE
if not os.getenv('OPENAI_BASE_URL') and not os.getenv('OPENAI_API_BASE'):
    os.environ['OPENAI_API_BASE'] = 'https://api.openai.com/v1'

# 不在源码中内置 API Key。请通过环境变量 / .env 提供。
if not API_KEY:
    API_KEY = ''

# 设置环境变量和OpenAI配置
if API_KEY:
    environ["OPENAI_API_KEY"] = API_KEY
    openai.api_key = API_KEY
    os.environ['OPENAI_API_KEY'] = API_KEY


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
