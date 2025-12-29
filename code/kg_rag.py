# -*- coding: utf-8 -*-

from os import getenv, environ
import re
import collections
import openai
from dotenv import load_dotenv
import json
import httpx
import os
import socket
import ssl
import urllib3
import certifi
import connexion
import pandas as pd
from langchain_community.vectorstores import Neo4jVector
from langchain_community.graphs import Neo4jGraph
from langchain_openai import OpenAIEmbeddings


def _as_problem(title: str, detail: str, status: int):
    """Build a RFC7807-like response body for Connexion."""
    return {"type": "about:blank", "title": title, "detail": detail, "status": status}

# 加载环境变量
load_dotenv()

# 从环境变量中读取密钥
API_KEY = getenv("OPENAI_API_KEY")
NEO4J_URL = getenv("NEO4J_URL")
NEO4J_USERNAME = getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = getenv("NEO4J_DATABASE")

# ===== 激进SSL绕过配置 =====
# 完全禁用SSL验证和警告
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''
os.environ['SSL_CERT_FILE'] = ''

# 禁用所有SSL验证
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 设置最低安全级别（允许弱加密）
ssl._DEFAULT_CIPHERS += ':!aNULL:!eNULL'
os.environ['OPENSSL_SECLEVEL'] = '0'

# OpenAI API base URL:
# - For official OpenAI, default is https://api.openai.com/v1
# - For mirror/proxy providers, set OPENAI_BASE_URL or OPENAI_API_BASE in .env
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

# ===== 创建完全绕过SSL的自定义HTTP客户端 =====
def create_insecure_ssl_context():
    """创建完全禁用SSL验证的SSL上下文"""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    
    # 设置最低安全要求
    try:
        context.set_ciphers('DEFAULT@SECLEVEL=0')  # 最低安全级别
    except:
        pass  # 如果设置失败，使用默认值
    
    # 使用现代的方式设置协议版本
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    
    return context

# 创建自定义传输层
def create_insecure_transport():
    """创建完全禁用SSL验证的传输层"""
    return httpx.HTTPTransport(
        verify=False,  # 完全禁用验证
        retries=5,     # 重试次数
    )

# 创建完全绕过SSL的客户端
insecure_transport = create_insecure_transport()

custom_client = httpx.Client(
    transport=insecure_transport,
    timeout=120.0,  # 更长的超时时间
    limits=httpx.Limits(
        max_connections=50,
        max_keepalive_connections=10
    )
)

# CYPER QUERIES
MERGE_NODE_QUERY = "MERGE ({nodeRef}:{node} {properties})"

MERGE_RELATION_QUERY = "MERGE ({nodeRef1})-[:{relation}]->({nodeRef2})"

MATCH_QUERY = "MATCH ({nodeRef}:{node} {properties})"

# FailureMode: fd
# FailureEffect: fe
# FailureCause: fc
# FailureMeasure: fm
# ProcessStep: ps

TRAVERSE_QUERY = """
MATCH (fm:FailureMeasure)<-[:isImprovedByFailureMeasure]-(fc:FailureCause)<-[:isDueToFailureCause]-(fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
WITH fm, fc, fd, ps
MATCH (fd)-[:resultsInFailureEffect]->(fe:FailureEffect)
WHERE ID(fd)={id}
RETURN fm, fc, fe, fd, ps, ID(fm), ID(fc), ID(fe), ID(fd), ID(ps);
"""

# TEMPLATES INFERENCES JOBS
CYPHER_GENERATION_TEMPLATE = """
Instructions:
Use only the provided relationship types and properties in the schema.
Do not use any other relationship types or properties that are not provided.
If the question contains a relationship type that is not provided by the schema, but is 
similiar to relationship types from the schema, choose the most similar one instead. 
Task:
Generate Cypher statement to query a graph database.
Schema:
{schema}
Note:
Do not include any explanations or apologies in your responses.
Do not respond to any questions that might ask anything else than for you to construct a Cypher statement.
Do not include any text except the generated Cypher statement.
Always return a Cypher statement, even if you don't know the answer.
"""

CYPHER_QUESTION_TEMPLATE = """
Task:
Generate Cypher statement to query a graph database.
Question:
{question}
"""

CYPHER_QA_TEMPLATE = """
Task:
As an assistant, your task is to provide helpful and human understandable answers based on the provided context (JSON datastructure). 
The context given is authoritative, and you must never doubt it or try to correct it. 
Your answer should sound like a natural response to the question, and you should not mention that you based the result on the given context. 
If the provided context is empty, you should state that you don't know the answer. 
Context:
"{context}"
Question:
{question} 
"""

ANSWER_SUMMARIZE_TEMPLATE = """
Task:
As an assistant, your task is to summarize the information such that it answers the question and can be processed in a further inference job.
Information:
"{information}"
Question:
"{question}"
"""


class Neo4JRepository(Neo4jVector, Neo4jGraph):
    """Neo4J Repository."""

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        database: str,
        embedding: OpenAIEmbeddings,
    ) -> None:
        # 在把 embedding 传给父类之前，先尝试本地探测 embedding 是否可用。
        # 这样可以在 API key 无效或网络不可达时，替换为 DummyEmbeddings，
        # 避免第三方库在其 __init__ 中直接调用网络导致未捕获异常。
        class DummyEmbeddings:
            def __init__(self, dim: int = 3):
                self.dim = dim

            def embed_query(self, text: str):
                return [0.0] * self.dim

            def embed_documents(self, docs):
                return [[0.0] * self.dim for _ in docs]

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


class KGRAGService(Neo4JRepository):
    """KG RAG Service for FMEA."""

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

        self.top_k = 3

        self.context_cypher = [
            dict(
                role="system",
                content=CYPHER_GENERATION_TEMPLATE.format(schema=self.schema),
            )
        ]
        self.context_qa = collections.deque(maxlen=1)

    @staticmethod
    def extract_cypher(text: str) -> str:
        """
        Extracts cypher from a string containing LLM output.

        Args:
            text (str): A string containing LLM output.

        Returns:
            str: The input string with quotes removed.
        """
        pattern = r"```(.*?)```"

        matches = re.findall(pattern, text, re.DOTALL)

        return matches[0] if matches else text.replace("\n", " ")

    @staticmethod
    def format_properties(properties: dict) -> str:
        """
        Formats a dictionary of properties into a string representation.

        Args:
            properties (dict): A dictionary of properties to format.

        Returns:
            str: A string representation of the formatted properties.
        """
        def _escape_str(v: object) -> str:
            return str(v).replace("\\", "\\\\").replace('"', '\\"')

        parts: list[str] = []
        numeric_keys = {"S", "O", "D", "RPN"}

        for key, value in properties.items():
            if value is None:
                continue

            if key in numeric_keys:
                try:
                    # 支持 int/float/字符串数字；尽量存为整数。
                    num = float(value)
                    if num.is_integer():
                        parts.append(f"{key}: {int(num)}")
                    else:
                        parts.append(f"{key}: {num}")
                except Exception:
                    parts.append(f'{key}: "{_escape_str(value)}"')
            else:
                parts.append(f'{key}: "{_escape_str(value)}"')

        return "{" + ", ".join(parts) + "}"

    def _is_graph_initialized(self) -> bool:
        """Return True if FailureMode nodes exist (graph loaded)."""
        try:
            result = self.query("MATCH (fd:FailureMode) RETURN count(fd) AS c")
            if not result:
                return False
            return int(result[0].get("c", 0)) > 0
        except Exception:
            return False

    def qa_prompt_context(self, question: str, context: str) -> None:
        """
        Adds a question and context to the QA context.

        Args:
            question (str): The question to be added.
            context (str): The context to be added.

        Returns:
            None
        """
        prompt = CYPHER_QA_TEMPLATE.format(
            context=context,
            question=question,
        )
        self.context_qa.append(dict(role="assistant", content=prompt))

    def cypher_prompt_context(self, question: str) -> None:
        """
        Adds a question to the Cypher context.

        Args:
            question (str): The question to be added.

        Returns:
            None
        """
        prompt = CYPHER_QUESTION_TEMPLATE.format(
            question=question,
        )
        if len(self.context_cypher) == 1:
            self.context_cypher.append(dict(role="system", content=prompt))
        else:
            self.context_cypher[1] = dict(role="system", content=prompt)

    def summarize_context(self, context: str, question: str):
        """
        Summarize the context.

        Args:
            context (str): The context to summarize.
            question (str): The question to summarize.

        Returns:
            dict: The summarized context.
        """
        prompt = ANSWER_SUMMARIZE_TEMPLATE.format(
            information=context, question=question
        )
        return dict(role="assistant", content=prompt)

    def set_top_k(self, top_k: int):
        """
        Set the top k value.

        Args:
            top_k (int): The top k value to set.

        Returns:
            true
        """
        self.top_k = top_k
        return True

    def run_inference(
        self, context: list[dict], temperature: float = 0.0, max_tokens: int = 4000
    ):
        """
        Run inference on the OpenAI API.

        Args:
            context (list): A list of dictionaries containing the context.
            temperature (float): The temperature to use for the inference.
            max_tokens (int): The maximum number of tokens to generate.

        Returns:
            str: The generated text.
        """
        model = getenv("OPENAI_MODEL", "gpt-4o-mini")
        api_base = getenv("OPENAI_API_BASE") or getenv("OPENAI_BASE_URL")

        # Preferred: OpenAI Python SDK v1+ (required by langchain_openai).
        # This returns a response object that still supports `.choices[0].message.content`.
        if hasattr(openai, "OpenAI"):
            client_kwargs = {}
            if API_KEY:
                client_kwargs["api_key"] = API_KEY
            if api_base:
                # v1 uses `base_url`
                client_kwargs["base_url"] = api_base

            client = openai.OpenAI(**client_kwargs)
            return client.chat.completions.create(
                model=model,
                messages=context,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # Fallback: legacy OpenAI Python SDK (<1.0).
        # Public OpenAI API uses `model=`, Azure deployments use `engine=`.
        engine = getenv("OPENAI_ENGINE") or getenv("OPENAI_DEPLOYMENT")
        legacy_kwargs = {
            "messages": context,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if engine:
            return openai.ChatCompletion.create(engine=engine, **legacy_kwargs)
        return openai.ChatCompletion.create(model=model, **legacy_kwargs)

    def traverse_graph(self, failureEffectId: str) -> list[dict]:
        """
        Returns a list of nodes and relations for a given failure measure id.

        Args:
            failureMeasureId (str): The failure measure id to traverse the graph for.

        Returns:
            list[dict]: A list of nodes and relations.
        """
        try:
            result = self.query(TRAVERSE_QUERY.format(id=failureEffectId))
            return result
        except Exception as e:
            print(e)

    def validate_cypher(self, cypher: str) -> bool:
        """
        Validate a Cypher query.

        Args:
            cypher (str): The Cypher query to validate.

        Returns:
            bool: True if the Cypher query is valid, False otherwise.
        """
        try:
            self.query(cypher)
            return True
        except Exception:
            return False

    def get_failure_mode_ids(self) -> list[dict]:
        """
        Get all failure effect ids.

        Returns:
            list[dict]: A list of failure effect ids.
        """
        try:
            result = self.query(
                """
                    MATCH (fd:FailureMode)
                    RETURN ID(fd);
                    """
            )
            return result
        except Exception as e:
            print(e)

    def get_failure_measure_ids(self) -> list[dict]:
        """
        Get all failure measure ids.

        Returns:
            list[dict]: A list of failure measure ids.
        """
        try:
            result = self.query(
                """
                    MATCH (fm:FailureMeasure)
                    RETURN ID(fm);
                    """
            )
            return result
        except Exception as e:
            print(e)

    def create_fmea_graph(self, csv_file: str) -> bool:
        """
        Create the FMEA graph.

        Args:
            csv_file (str): The path to the csv file containing the FMEA data.

        Returns:
            bool: True if the graph was created successfully, False otherwise.

        """
        df = pd.read_csv(csv_file, delimiter=";", encoding="utf-8")

        # Create nodes and relations
        for _, row in df.iterrows():
            nodes = [
                MERGE_NODE_QUERY.format(
                    nodeRef="FailureMode",
                    node="FailureMode",
                    properties=self.format_properties(
                        {
                            "FailureMode": row["FailureMode"],
                            "RPN": row["RPN"],
                        }
                    ),
                ),
                MERGE_NODE_QUERY.format(
                    nodeRef="ProcessStep",
                    node="ProcessStep",
                    properties=self.format_properties(
                        {"ProcessStep": row["ProcessStep"]}
                    ),
                ),
                MERGE_NODE_QUERY.format(
                    nodeRef="FailureEffect",
                    node="FailureEffect",
                    properties=self.format_properties(
                        {
                            "FailureEffect": row["FailureEffect"],
                            "S": row["S"],
                        }
                    ),
                ),
                MERGE_NODE_QUERY.format(
                    nodeRef="FailureCause",
                    node="FailureCause",
                    properties=self.format_properties(
                        {
                            "FailureCause": row["FailureCause"],
                            "O": row["O"],
                        }
                    ),
                ),
                MERGE_NODE_QUERY.format(
                    nodeRef="FailureMeasure",
                    node="FailureMeasure",
                    properties=self.format_properties(
                        {
                            "FailureMeasure": row["FailureMeasure"],
                            "DetectionMeasure": row["DetectionMeasure"],
                            "D": row["D"],
                        }
                    ),
                ),
            ]

            relations = [
                MERGE_RELATION_QUERY.format(
                    nodeRef1="FailureMode",
                    relation="occursAtProcessStep",
                    nodeRef2="ProcessStep",
                ),
                MERGE_RELATION_QUERY.format(
                    nodeRef1="FailureMode",
                    relation="resultsInFailureEffect",
                    nodeRef2="FailureEffect",
                ),
                MERGE_RELATION_QUERY.format(
                    nodeRef1="FailureMode",
                    relation="isDueToFailureCause",
                    nodeRef2="FailureCause",
                ),
                MERGE_RELATION_QUERY.format(
                    nodeRef1="FailureCause",
                    relation="isImprovedByFailureMeasure",
                    nodeRef2="FailureMeasure",
                ),
            ]

            query = " \n ".join(nodes + relations)

            try:
                self.query(query)
            except Exception:
                return False

        # Create vector embeddings
        self.create_vector_embeddings()

        return True

    def create_vector_embeddings(self) -> bool:
        """
        Create vector embeddings for the FMEA graph.

        Returns:
            bool: True if the vector embeddings were created successfully, False otherwise.
        """
        # Get all failure mode ids
        failureModeIds = self.get_failure_mode_ids()

        # Check if the index already exists
        embedding_dimension = self.retrieve_existing_index()

        # If the index doesn't exist
        if not embedding_dimension:
            self.create_new_index()

        # Add the failure measures to the index
        for entry in failureModeIds:
            id = entry["ID(fd)"]
            nodes = self.traverse_graph(str(id))
            chunk, nodeIds = self.create_chunk(nodes)

            embeddedNodeId = self.add_texts([chunk], metadatas=[nodeIds])[0]

            query = [
                MATCH_QUERY.format(
                    nodeRef="index",
                    node="Chunk",
                    properties=self.format_properties({"id": embeddedNodeId}),
                ),
                "WITH index ",
                MATCH_QUERY.format(
                    nodeRef="fd",
                    node="FailureMode",
                    properties=self.format_properties({}),
                ),
                "WHERE ID(fd)={id}".format(id=id),
                MERGE_RELATION_QUERY.format(
                    nodeRef1="fd",
                    relation="isIndexed",
                    nodeRef2="index",
                ),
            ]

            try:
                self.query("\n".join(query))
            except Exception as e:
                raise e

        return True

    def create_chunk(self, nodes: list[dict]) -> str:
        """
        Create a chunk from a list of nodes.

        Args:
            nodes (list[dict]): A list of nodes.

        Returns:
            str: The chunk.
        """
        fm, fc, fe, fd, ps = [[] for _ in range(5)]

        nodeIds = {
            "failureModeIds": [],
            "failureEffectIds": [],
            "failureCauseIds": [],
            "failureMeasureIds": [],
            "processStepIds": [],
        }

        for node in nodes:
            if node["fm"] not in fm:
                fm.append(node["fm"])
                nodeIds["failureMeasureIds"].append(node["ID(fm)"])
            if node["fc"] not in fc:
                fc.append(node["fc"])
                nodeIds["failureCauseIds"].append(node["ID(fc)"])
            if node["fe"] not in fe:
                fe.append(node["fe"])
                nodeIds["failureEffectIds"].append(node["ID(fe)"])
            if node["fd"] not in fd:
                fd.append(node["fd"])
                nodeIds["failureModeIds"].append(node["ID(fd)"])
            if node["ps"] not in ps:
                ps.append(node["ps"])
                nodeIds["processStepIds"].append(node["ID(ps)"])

        chunk = (
            ", ".join("ProcessStep: " + i["ProcessStep"] for i in ps)
            + "".join(
                ", FailureMode: " + i["FailureMode"] + ", RPN: " + str(i["RPN"])
                for i in fd
            )
            + "".join(
                ", FailureEffect: " + i["FailureEffect"] + ", S: " + str(i["S"])
                for i in fe
            )
            + "".join(
                ", FailureCause: " + i["FailureCause"] + ", O: " + str(i["O"])
                for i in fc
            )
            + "".join(
                ", FailureMeasure: "
                + i["FailureMeasure"]
                + ", DetectionMeasure: "
                + i["DetectionMeasure"]
                + ", D: "
                + str(i["D"])
                for i in fm
            )
        )

        return chunk, nodeIds

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

        if not self._is_graph_initialized():
            raise RuntimeError(
                "知识图谱尚未初始化：请先调用 /api/v1/create-fmea-graph 将 CSV 导入 Neo4j 并建立向量索引。"
            )

        # List pre answers
        pre_answer = list()

        # Add question to cypher context
        self.cypher_prompt_context(question)

        # Run inference
        result = self.run_inference(self.context_cypher)

        # Extract cypher query
        cypher_query = self.extract_cypher(result.choices[0].message.content)

        # Check if cypher query is valid
        if self.validate_cypher(cypher_query):
            query_result = self.query(cypher_query)
            if len(query_result) > self.top_k:
                query_result = query_result[: self.top_k]
        else:
            query_result = None

        if not query_result:
            # Vector search
            results = self.similarity_search(question, k=self.top_k)
            query_result = [result.page_content for result in results]

        # Summarize the query results for further processing
        for result in query_result:
            result_summarize = self.run_inference(
                [self.summarize_context(context=json.dumps(result), question=question)]
            )
            pre_answer.append(result_summarize.choices[0].message.content)

        # Add question and context to QA context
        self.qa_prompt_context(question, json.dumps(pre_answer, ensure_ascii=False))

        # Run inference
        answer = self.run_inference(list(self.context_qa), temperature=1.0)

        return {
            "answer": answer.choices[0].message.content,
            "context": pre_answer,
            "context_raw": query_result,
        }


# RAG SERVICE
rag_service = KGRAGService()


# API ENDPOINTS
def create_graph(body: object):
    try:
        path = body.get("path") if isinstance(body, dict) else None
        if not path:
            return _as_problem("Bad Request", "缺少字段: path", 400), 400
        ok = rag_service.create_fmea_graph(csv_file=path)
        if not ok:
            return _as_problem("Internal Server Error", "建图失败：请检查 CSV 路径、Neo4j 连接与写入权限。", 500), 500
        return True
    except Exception as e:
        return _as_problem("Internal Server Error", f"建图异常：{e}", 500), 500


def answer_question(body: object):
    try:
        question = body.get("question") if isinstance(body, dict) else None
        if question is None:
            return _as_problem("Bad Request", "缺少字段: question", 400), 400
        return rag_service.answer_question(str(question))
    except ValueError as e:
        return _as_problem("Bad Request", str(e), 400), 400
    except RuntimeError as e:
        msg = str(e)
        # 业务前置条件未满足：未建图/未初始化
        if "知识图谱尚未初始化" in msg:
            return _as_problem("Conflict", msg, 409), 409
        return _as_problem("Internal Server Error", f"问答异常：{msg}", 500), 500
    except Exception as e:
        return _as_problem("Internal Server Error", f"问答异常：{e}", 500), 500


def set_top_k(body: object):
    try:
        top_k = body.get("top_k") if isinstance(body, dict) else None
        if top_k is None:
            return _as_problem("Bad Request", "缺少字段: top_k", 400), 400
        return rag_service.set_top_k(int(top_k))
    except Exception as e:
        return _as_problem("Bad Request", f"top_k 非法：{e}", 400), 400


# MAIN ENTRYPOINT
if __name__ == "__main__":
    app = connexion.FlaskApp(__name__)
    app.add_api("api.yml")
    application = app.app
    app.run(port=8080)