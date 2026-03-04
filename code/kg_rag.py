# -*- coding: utf-8 -*-

# 环境变量管理（dotenv, os）
# HTTP客户端（httpx）
# 图数据库（Neo4j相关）
# AI模型（OpenAI, LangChain）
# Web框架（connexion - 基于Flask的OpenAPI框架）
from os import getenv, environ
from datetime import datetime
import time
import re
import collections
import openai
from dotenv import load_dotenv
import json
import httpx
import os
from pathlib import Path
import socket
import ssl
import urllib3
import certifi
import connexion
import pandas as pd
from langchain_community.vectorstores import Neo4jVector
from langchain_community.graphs import Neo4jGraph
from langchain_openai import OpenAIEmbeddings
from urllib.parse import urlparse
import threading


def _as_problem(title: str, detail: str, status: int):
    """Build a RFC7807-like response body for Connexion."""
    return {"type": "about:blank", "title": title, "detail": detail, "status": status}


def _json_response(body: object, status: int = 200):
    """Return a Connexion response payload.

    Important: do NOT json.dumps here.
    Connexion/Flask will serialize dict/list to JSON. If we pre-serialize to a string,
    Connexion may serialize again, resulting in a JSON *string* that contains JSON.
    """
    return body, status

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

#定义三个Cypher字符串模板
# CYPER QUERIES
MERGE_NODE_QUERY = "MERGE ({nodeRef}:{node} {properties})"

MERGE_RELATION_QUERY = "MERGE ({nodeRef1})-[:{relation}]->({nodeRef2})"

MATCH_QUERY = "MATCH ({nodeRef}:{node} {properties})"

# FailureMode: fd
# FailureEffect: fe
# FailureCause: fc
# FailureMeasure: fm
# ProcessStep: ps

#———————————————————提示词模板———————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————

# 包含4个核心模板：
# CYPHER_GENERATION_TEMPLATE：根据schema生成Cypher查询
# CYPHER_QUESTION_TEMPLATE：将问题转换为Cypher查询
# CYPHER_QA_TEMPLATE：基于上下文回答问题的模板
# ANSWER_SUMMARIZE_TEMPLATE：信息总结模板

TRAVERSE_QUERY = """
MATCH (fm:FailureMeasure)<-[:isImprovedByFailureMeasure]-(fc:FailureCause)<-[:isDueToFailureCause]-(fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
WITH fm, fc, fd, ps
MATCH (fd)-[:resultsInFailureEffect]->(fe:FailureEffect)
WHERE ID(fd)={id}
RETURN fm, fc, fe, fd, ps, ID(fm), ID(fc), ID(fe), ID(fd), ID(ps);
"""

# TEMPLATES INFERENCES JOBS
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

#——————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————————

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

class KGRAGService(Neo4JRepository):
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

        super().__init__( # 调用的是 Neo4JRepository.__init__。
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

        self.top_k = 3 # 默认每次最多用 3 条“上下文/证据”来回答问题

        #给当前服务对象创建一个“消息列表”，专门用于后面让大模型生成 Cypher 查询语句。
        #把neo4j的schema注入到提示词里，让模型知道图里有什么样的节点、关系和属性，可以用来构造查询。
        self.context_cypher = [
            dict(
                role="system", # system角色的提示词
                content=CYPHER_GENERATION_TEMPLATE.format(schema=self.schema), # 消息的具体文本
            )
        ]
        self.context_qa = collections.deque(maxlen=1)
        self._dfmea_cache_path: str | None = None
        self._dfmea_cache_df: pd.DataFrame | None = None

    @staticmethod
    def _default_dfmea_csv_path() -> str | None:
        try:
            p = Path(__file__).resolve().parent.parent / "data" / "dfmea_final.csv"
            return str(p) if p.exists() else None
        except Exception:
            return None

    @staticmethod
    def _read_dfmea_csv(csv_file: str) -> pd.DataFrame | None:
        def _detect_delimiter(path: str) -> str:
            try:
                with open(path, "rb") as f:
                    sample = f.read(4096)
                text = sample.decode("utf-8-sig", errors="ignore")
                first_line = text.splitlines()[0] if text else ""
                candidates = [",", ";", "\t"]
                counts = {c: first_line.count(c) for c in candidates}
                best = max(counts, key=counts.get)
                return best if counts[best] > 0 else ";"
            except Exception:
                return ";"

        delimiter = _detect_delimiter(csv_file)
        df = None
        for enc in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                df = pd.read_csv(csv_file, delimiter=delimiter, encoding=enc)
                break
            except Exception:
                continue
        if df is None:
            return None

        df.columns = [str(c).strip() for c in df.columns]

        def _norm_col(name: object) -> str:
            return re.sub(r"\s+", "", str(name or "")).strip()

        col_map = {
            "设计项目": "ProcessStep",
            "过程步骤": "ProcessStep",
            "工序": "ProcessStep",
            "潜在的失效模式": "FailureMode",
            "潜在失效模式": "FailureMode",
            "潜在的失效后果": "FailureEffect",
            "潜在失效后果": "FailureEffect",
            "潜在的失效原因/机理": "FailureCause",
            "潜在失效原因/机理": "FailureCause",
            "潜在的失效原因": "FailureCause",
            "潜在失效原因": "FailureCause",
            "严重度": "S",
            "频度数": "O",
            "发生度": "O",
            "探测度数": "D",
            "探测度": "D",
            "RPN": "RPN",
            "现行探测性设计控制": "DetectionMeasure",
            "现行探测性控制": "DetectionMeasure",
            "临时采取的措施": "FailureMeasure",
            "现行预防性设计控制": "PreventControl",
        }

        rename: dict[str, str] = {}
        existing_cols = set(df.columns)
        for original in list(df.columns):
            target = col_map.get(_norm_col(original))
            if not target or target == original:
                continue
            if target in existing_cols:
                continue
            rename[original] = target
        if rename:
            df = df.rename(columns=rename)

        if "ProcessStep" in df.columns:
            df["ProcessStep"] = df["ProcessStep"].ffill()

        return df

    def _get_default_dfmea_df(self) -> pd.DataFrame | None:
        path = self._default_dfmea_csv_path()
        if not path:
            return None
        if self._dfmea_cache_df is not None and self._dfmea_cache_path == path:
            return self._dfmea_cache_df
        df = self._read_dfmea_csv(path)
        self._dfmea_cache_path = path
        self._dfmea_cache_df = df
        return df

    def _ensure_vector_index(self) -> None:
        """Ensure the Neo4j VECTOR index exists (and is ONLINE).

        Why: Neo4jVector.similarity_search will call `db.index.vector.queryNodes`
        with `index_name` (default: 'vector'). If the index doesn't exist, Neo4j
        raises: IllegalArgumentException: There is no such vector schema index.
        """
        self._ensure_neo4j_available()

        index_name = getattr(self, "vector_index_name", "vector") or "vector"
        node_label = getattr(self, "vector_node_label", "Chunk") or "Chunk"
        embedding_prop = getattr(self, "vector_embedding_property", "embedding") or "embedding"

        def _get_state() -> str | None:
            try:
                rows = self.query(
                    """
                    SHOW INDEXES YIELD name, type, state
                    WHERE name = $name
                    RETURN type, state
                    """,
                    params={"name": index_name},
                )
                if not rows:
                    return None
                # Neo4j 返回 type=\"VECTOR\" state=\"ONLINE\" 等
                return str(rows[0].get("state")) if rows[0].get("type") == "VECTOR" else None
            except TypeError:
                # 兼容 Neo4jGraph.query 不支持 params 的版本：降级为字符串拼接（index_name 来自 env，风险可控）
                rows = self.query(
                    "SHOW INDEXES YIELD name, type, state WHERE name = '" + str(index_name).replace("'", "\\'") + "' RETURN type, state"
                )
                if not rows:
                    return None
                return str(rows[0].get("state")) if rows[0].get("type") == "VECTOR" else None
            except Exception:
                return None

        state = _get_state()
        if state == "ONLINE":
            return

        # 不存在则尝试创建。优先用 langchain 内置 create_new_index（与自身配置一致）；
        # 若失败则用原生 Cypher 创建。
        if state is None:
            created = False
            try:
                # create_new_index 会使用 self.index_name/node_label/embedding_node_property
                # 而这些我们在 Neo4JRepository.__init__ 里已经传入/默认一致。
                self.create_new_index()
                created = True
            except Exception:
                created = False

            if not created:
                # 维度通过 embeddings 探测（DummyEmbeddings 下会是 3）
                dim = 1536
                try:
                    emb = getattr(self, "embedding", None)
                    if emb is not None:
                        dim = len(emb.embed_query("dim_probe"))
                except Exception:
                    dim = 1536

                cypher = (
                    "CREATE VECTOR INDEX `" + str(index_name).replace("`", "") + "` IF NOT EXISTS "
                    "FOR (n:`" + str(node_label).replace("`", "") + "`) ON (n.`" + str(embedding_prop).replace("`", "") + "`) "
                    "OPTIONS {indexConfig: {`vector.dimensions`: " + str(int(dim)) + ", `vector.similarity_function`: 'cosine'}}"
                )
                try:
                    self.query(cypher)
                except Exception as e:
                    raise RuntimeError(
                        f"向量索引不存在且自动创建失败：{e}。"
                        f"请确认连接到正确的 NEO4J_DATABASE，并且账号有 CREATE INDEX 权限。"
                    ) from e

        # 等待索引 ONLINE（Aura/远程库可能需要几秒）
        for i in range(12):
            state = _get_state()
            if state == "ONLINE":
                return
            time.sleep(0.5 + 0.2 * i)

        raise RuntimeError(
            f"向量索引 `{index_name}` 未就绪（state={state}）。请稍后重试，或在 Neo4j 中执行 SHOW INDEXES 查看索引状态。"
        )

    def clear_fmea_graph(self) -> dict:
        """Clear FMEA-related data from Neo4j.

        Scope: only labels/indexes created by this project.
        This is intended to prevent duplicate/dirty data when importing CSV multiple times.
        """
        self._ensure_neo4j_available()

        # 1) Drop indexes used by langchain Neo4jVector (best-effort)
        vector_index_name = getattr(self, "vector_index_name", None) or getenv("NEO4J_VECTOR_INDEX_NAME", "vector")
        keyword_index_name = getenv("NEO4J_KEYWORD_INDEX_NAME", "keyword")
        indexes_to_drop = [vector_index_name, keyword_index_name]
        dropped_indexes: list[str] = []
        drop_errors: list[str] = []

        for idx_name in indexes_to_drop:
            if not idx_name:
                continue
            safe = str(idx_name).replace("`", "")
            try:
                self.query(f"DROP INDEX `{safe}` IF EXISTS")
                dropped_indexes.append(safe)
            except Exception as e:
                # 不把错误当作致命：有的 Neo4j 版本不支持 IF EXISTS 或权限不足
                drop_errors.append(f"{safe}: {e}")

        # 2) Delete nodes/relationships for this project's labels
        labels = [
            "Chunk",
            "FailureMode",
            "FailureEffect",
            "FailureCause",
            "FailureMeasure",
            "ProcessStep",
        ]

        deleted: dict[str, int] = {}
        delete_errors: list[str] = []

        for label in labels:
            safe_label = str(label).replace("`", "")
            try:
                cnt_rows = self.query(f"MATCH (n:`{safe_label}`) RETURN count(n) AS c")
                cnt = int(cnt_rows[0].get("c", 0)) if cnt_rows else 0
                if cnt:
                    self.query(f"MATCH (n:`{safe_label}`) DETACH DELETE n")
                deleted[safe_label] = cnt
            except Exception as e:
                delete_errors.append(f"{safe_label}: {e}")

        # 尝试刷新 schema，避免后续 LLM 生成 Cypher 时 schema 过期
        try:
            self.refresh_schema()
        except Exception:
            pass

        return {
            "ok": True,
            "dropped_indexes": dropped_indexes,
            "drop_errors": drop_errors,
            "deleted": deleted,
            "delete_errors": delete_errors,
        }

    def _ensure_neo4j_available(self) -> None:
        def _is_transient(e: Exception) -> bool:
            msg = str(e) or ""
            patterns = (
                "Unable to retrieve routing information",
                "defunct connection",
                "Failed to read from defunct connection",
                "Transaction failed and will be retried",
                "ServiceUnavailable",
                "SessionExpired",
                "connection error",
            )
            return any(p.lower() in msg.lower() for p in patterns)

        last_err: Exception | None = None
        # Neo4j Aura/集群在首次连接时有概率出现路由表拉取失败/连接池建立抖动。
        # 这里做小步重试，避免“第一次提问 500，第二次就好了”的体验。
        for attempt in range(1, 4):
            try:
                _ = self.query("RETURN 1 AS ok")
                return
            except Exception as e:
                last_err = e
                if attempt < 3 and _is_transient(e):
                    time.sleep(0.6 * attempt)
                    continue
                raise RuntimeError(f"Neo4j 连接失败：{e}") from e

        # 理论上不会走到这里；兜底
        raise RuntimeError(f"Neo4j 连接失败：{last_err}")

    @staticmethod
    def _save_answer_to_file(answer_text: str) -> str:
        timestamp = datetime.now().strftime("%y%m%d_%H_%M")
        base_filename = f"{timestamp}.txt"

        default_dir = os.path.join(os.getcwd(), "answer")
        output_dir = os.getenv("ANSWER_OUTPUT_DIR", default_dir)
        os.makedirs(output_dir, exist_ok=True)

        file_path = os.path.join(output_dir, base_filename)
        if os.path.exists(file_path):
            # 同一分钟多次提问：避免覆盖/混写，追加一个自增序号
            idx = 1
            while True:
                candidate = os.path.join(output_dir, f"{timestamp}_{idx:02d}.txt")
                if not os.path.exists(candidate):
                    file_path = candidate
                    break
                idx += 1

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(str(answer_text))
            f.write("\n")

        return file_path

    @staticmethod # 静态方法
    # 从大模型输出文本里提取 ... 代码块中的 Cypher 语句，用于后续 self.query(cypher_query) 执行查询
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
    # 把一个 Python 字典，转换成一段可以直接拼进 Neo4j Cypher 的“属性 map 字面量”字符串
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

    # 参数：无（仅用 self 查询）；返回：bool；功能：检查 Neo4j 中是否已有 FailureMode 节点，用于判断知识图谱是否已初始化。
    def _is_graph_initialized(self) -> bool:
        """Return True if FailureMode nodes exist (graph loaded)."""
        try:
            result = self.query("MATCH (fd:FailureMode) RETURN count(fd) AS c")
            if not result:
                return False
            return int(result[0].get("c", 0)) > 0
        except Exception:
            return False

    # 参数：question(str)、context(str)；返回：None；功能：把“问题+上下文”按模板拼成提示词，存入 self.context_qa 供后续回答使用。
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

    # 参数：question(str)；返回：None；功能：把问题按模板写入/更新 self.context_cypher，用于让模型生成对应的 Cypher 查询。
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

    # 参数：context(str)、question(str)；返回：dict；功能：生成一条“请总结信息以回答问题”的提示消息，供 run_inference 调用。
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

    # 参数：top_k(int)；返回：True；功能：设置检索/截断时取前多少条（Top-K），影响图查询结果截断和向量检索返回数量。
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

    # 最关键的“直接调用大模型 API”的函数：它把 messages=context 发给 OpenAI，然后把模型返回的补全结果对象原样返回。
    # 参数：context(list[dict])、temperature(float)、max_tokens(int)；返回：OpenAI 聊天补全结果对象；功能：调用 OpenAI 接口让模型基于上下文生成内容。
    def run_inference(
        self, context: list[dict], temperature: float = 0.0, max_tokens: int = 4000
    ):
        """
        调用 OpenAI 接口进行推理（生成回复）。

        Args:
            context (list): 消息上下文列表（每项为 dict，包含 role/content 等字段）。
            temperature (float): 生成随机性，越大越发散。
            max_tokens (int): 最大生成 token 数。

        Returns:
            object: OpenAI 聊天补全结果对象（可通过 choices[0].message.content 取文本）。
        """
        model = getenv("OPENAI_MODEL", "gpt-4o-mini")
        api_base = getenv("OPENAI_API_BASE") or getenv("OPENAI_BASE_URL")

        # 优先使用：OpenAI Python SDK v1+（langchain_openai 依赖该版本）。
        # 返回的是响应对象，仍可通过 `.choices[0].message.content` 读取生成文本。
        if hasattr(openai, "OpenAI"):
            client_kwargs = {}
            if API_KEY:
                client_kwargs["api_key"] = API_KEY
            if api_base:
                # v1 版本使用参数名 `base_url`
                client_kwargs["base_url"] = api_base

            client = openai.OpenAI(**client_kwargs)
            return client.chat.completions.create(
                model=model,
                messages=context,
                temperature=temperature,
                max_tokens=max_tokens,
            )

        # 兜底方案：旧版 OpenAI Python SDK（<1.0）。
        # 公有 OpenAI 一般用 `model=`；Azure OpenAI 部署通常用 `engine=`。
        engine = getenv("OPENAI_ENGINE") or getenv("OPENAI_DEPLOYMENT")
        legacy_kwargs = {
            "messages": context,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if engine:
            return openai.ChatCompletion.create(engine=engine, **legacy_kwargs)
        return openai.ChatCompletion.create(model=model, **legacy_kwargs)

    # 把“图里的一个 FailureMode（失效模式）周围相关联的信息”取出来，拼成一段可被向量化的文本，用来建立向量索引（RAG 的检索库）。
    # 参数：failureEffectId(str)；返回：list[dict]；功能：执行 TRAVERSE_QUERY，按给定节点 ID 从图中查出相关节点/关系的记录列表。
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

    # 参数：cypher(str)；返回：bool；功能：用 self.query 试跑一次 Cypher，能执行则返回 True，执行报错则返回 False。
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

    # 参数：无（仅用 self 查询）；返回：list[dict]；功能：查询所有 FailureMode 节点的 Neo4j 内部 ID 列表。
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

    # 参数：无（仅用 self 查询）；返回：list[dict]；功能：查询所有 FailureMeasure 节点的 Neo4j 内部 ID 列表。
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

    # 一个用从CSV文件创建FMEA节点的方法
    def create_fmea_graph(self, csv_file: str) -> bool:
        """
        Create the FMEA graph.

        Args:
            csv_file (str): The path to the csv file containing the FMEA data.

        Returns:
            bool: True if the graph was created successfully, False otherwise.

        """
        def _detect_delimiter(path: str) -> str:
            try:
                with open(path, "rb") as f:
                    sample = f.read(4096)
                text = sample.decode("utf-8-sig", errors="ignore")
                first_line = text.splitlines()[0] if text else ""
                candidates = [",", ";", "\t"]
                counts = {c: first_line.count(c) for c in candidates}
                best = max(counts, key=counts.get)
                return best if counts[best] > 0 else ";"
            except Exception:
                return ";"

        self._ensure_neo4j_available()

        delimiter = _detect_delimiter(csv_file)
        df = None
        for enc in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                df = pd.read_csv(csv_file, delimiter=delimiter, encoding=enc)
                break
            except Exception:
                continue
        if df is None:
            return False

        # 规范化列名（去 BOM / 去首尾空格）
        df.columns = [str(c).strip() for c in df.columns]

        # 支持中文表头映射到内部字段
        # 注意：真实 CSV 可能同时包含少量英文列名（例如 RPN），但关键列（FailureMode/ProcessStep）仍是中文。
        # 因此这里不应以“是否出现任意一个英文列名”来决定是否做映射；而是始终尝试按映射表重命名。
        def _norm_col(name: object) -> str:
            # 去掉所有空白字符（含换行），避免类似 “潜在的失效原因\n/机理” 的情况匹配失败
            return re.sub(r"\s+", "", str(name or "")).strip()

        col_map = {
            # 工序/项目
            "设计项目": "ProcessStep",
            "过程步骤": "ProcessStep",
            "工序": "ProcessStep",
            # 失效相关
            "潜在的失效模式": "FailureMode",
            "潜在失效模式": "FailureMode",
            "潜在的失效后果": "FailureEffect",
            "潜在失效后果": "FailureEffect",
            "潜在的失效原因/机理": "FailureCause",
            "潜在失效原因/机理": "FailureCause",
            "潜在的失效原因": "FailureCause",
            "潜在失效原因": "FailureCause",
            # 评分
            "严重度": "S",
            "频度数": "O",
            "发生度": "O",
            "探测度数": "D",
            "探测度": "D",
            "RPN": "RPN",
            # 控制/措施
            "现行探测性设计控制": "DetectionMeasure",
            "现行探测性控制": "DetectionMeasure",
            # 临时措施更贴近“改进措施”语义，作为 FailureMeasure
            "临时采取的措施": "FailureMeasure",
            # 预防性控制保留用于组合进 FailureMeasure
            "现行预防性设计控制": "PreventControl",
        }

        # 基于“规范化后的列名”做匹配，允许原始列名包含换行/多空格
        rename: dict[str, str] = {}
        existing_cols = set(df.columns)
        for original in list(df.columns):
            target = col_map.get(_norm_col(original))
            if not target:
                continue
            if target == original:
                continue
            # 如果目标列已存在（例如中英双列同时存在），避免覆盖；保留现有目标列
            if target in existing_cols:
                continue
            rename[original] = target

        if rename:
            df = df.rename(columns=rename)

        # 常见 DFMEA：同一“设计项目”可能只在第一行填写，后续行为空，需要向下填充
        if "ProcessStep" in df.columns:
            df["ProcessStep"] = df["ProcessStep"].ffill()

        # 把“预防性控制”合并到 FailureMeasure 字段，避免信息丢失
        # 同时保留原始“临时措施”到 TempMeasure，便于后续做确定性问答时区分语义。
        if "FailureMeasure" in df.columns and "TempMeasure" not in df.columns:
            df["TempMeasure"] = df["FailureMeasure"]

        if "PreventControl" in df.columns:
            fm = df["FailureMeasure"] if "FailureMeasure" in df.columns else ""
            fm = fm.fillna("").astype(str).str.strip()
            pc = df["PreventControl"].fillna("").astype(str).str.strip()

            combined = []
            for a, b in zip(pc.tolist(), fm.tolist()):
                a = a.strip() if isinstance(a, str) else ""
                b = b.strip() if isinstance(b, str) else ""
                if a and b:
                    combined.append(f"预防控制：{a}；临时/改进措施：{b}")
                elif a:
                    combined.append(f"预防控制：{a}")
                elif b:
                    combined.append(b)
                else:
                    combined.append("")

            df["FailureMeasure"] = combined

        # 建图最小必要字段检查（避免“建图返回 true 但实际没写入”）
        if "FailureMode" not in df.columns or "ProcessStep" not in df.columns:
            return False

        # 如果缺少 RPN，但有 S/O/D，则计算 RPN
        if "RPN" not in df.columns and {"S", "O", "D"}.issubset(set(df.columns)):
            def _safe_num(x):
                try:
                    return float(x)
                except Exception:
                    return None

            rpn_vals = []
            for s, o, d in zip(df["S"].tolist(), df["O"].tolist(), df["D"].tolist()):
                ns, no, nd = _safe_num(s), _safe_num(o), _safe_num(d)
                rpn_vals.append(int(ns * no * nd) if ns is not None and no is not None and nd is not None else None)
            df["RPN"] = rpn_vals

        def _to_none_if_blank(v: object):
            if v is None:
                return None
            if isinstance(v, float) and pd.isna(v):
                return None
            s = str(v).strip()
            return s if s else None

        # Create nodes and relations
        inserted_rows = 0
        for _, row in df.iterrows():
            failure_mode = _to_none_if_blank(row.get("FailureMode"))
            process_step = _to_none_if_blank(row.get("ProcessStep"))
            if not failure_mode or not process_step:
                # 这两列是建图的最小必要字段
                continue

            prevent_control = _to_none_if_blank(row.get("PreventControl"))
            detect_control = _to_none_if_blank(row.get("DetectionMeasure"))
            temp_measure = _to_none_if_blank(row.get("TempMeasure"))

            rpn = row.get("RPN")
            s_val = row.get("S")
            o_val = row.get("O")
            d_val = row.get("D")

            nodes: list[str] = []
            relations: list[str] = []

            nodes.append(
                MERGE_NODE_QUERY.format(
                    nodeRef="ProcessStep",
                    node="ProcessStep",
                    properties=self.format_properties({"ProcessStep": process_step}),
                )
            )

            nodes.append(
                MERGE_NODE_QUERY.format(
                    nodeRef="FailureMode",
                    node="FailureMode",
                    # 把 S/O/D 同步写到 FailureMode 上，方便做“按工序统计平均严重度/频度/探测度”等确定性查询。
                    # 同时避免 FailureEffect/FailureCause 节点因 MERGE(按文本)被跨工序复用而导致数值串味。
                    properties=self.format_properties(
                        {
                            "FailureMode": failure_mode,
                            "RPN": rpn,
                            "S": s_val,
                            "O": o_val,
                            "D": d_val,
                            # 为确定性问答保留原始控制字段（跨不同 FMEA 表更稳定）
                            "PreventControl": prevent_control,
                            "DetectionMeasure": detect_control,
                            "TempMeasure": temp_measure,
                        }
                    ),
                )
            )
            relations.append(
                MERGE_RELATION_QUERY.format(
                    nodeRef1="FailureMode",
                    relation="occursAtProcessStep",
                    nodeRef2="ProcessStep",
                )
            )

            failure_effect = _to_none_if_blank(row.get("FailureEffect"))
            if failure_effect:
                nodes.append(
                    MERGE_NODE_QUERY.format(
                        nodeRef="FailureEffect",
                        node="FailureEffect",
                        properties=self.format_properties({"FailureEffect": failure_effect, "S": s_val}),
                    )
                )
                relations.append(
                    MERGE_RELATION_QUERY.format(
                        nodeRef1="FailureMode",
                        relation="resultsInFailureEffect",
                        nodeRef2="FailureEffect",
                    )
                )

            failure_cause = _to_none_if_blank(row.get("FailureCause"))
            if failure_cause:
                nodes.append(
                    MERGE_NODE_QUERY.format(
                        nodeRef="FailureCause",
                        node="FailureCause",
                        properties=self.format_properties({"FailureCause": failure_cause, "O": o_val}),
                    )
                )
                relations.append(
                    MERGE_RELATION_QUERY.format(
                        nodeRef1="FailureMode",
                        relation="isDueToFailureCause",
                        nodeRef2="FailureCause",
                    )
                )

            failure_measure = _to_none_if_blank(row.get("FailureMeasure"))
            detection_measure = _to_none_if_blank(row.get("DetectionMeasure"))
            if failure_measure or detection_measure or (d_val is not None and not (isinstance(d_val, float) and pd.isna(d_val))):
                nodes.append(
                    MERGE_NODE_QUERY.format(
                        nodeRef="FailureMeasure",
                        node="FailureMeasure",
                        properties=self.format_properties(
                            {
                                "FailureMeasure": failure_measure,
                                "DetectionMeasure": detection_measure,
                                "D": d_val,
                            }
                        ),
                    )
                )
                if failure_cause:
                    relations.append(
                        MERGE_RELATION_QUERY.format(
                            nodeRef1="FailureCause",
                            relation="isImprovedByFailureMeasure",
                            nodeRef2="FailureMeasure",
                        )
                    )

            query = "\n".join(nodes + relations)

            try:
                self.query(query)
            except Exception:
                return False

            inserted_rows += 1

        # 如果一行都没插入，说明 CSV 列映射或内容有问题，直接失败，避免误报成功
        if inserted_rows == 0:
            return False

        # Create vector embeddings
        self.create_vector_embeddings()

        return True

    # 在已经把 FMEA 的节点/关系写进 Neo4j 之后，再把每个失效模式相关的一坨信息“打包成文本 → 向量化 → 存到 Neo4j 的向量索引里
    def create_vector_embeddings(self) -> bool:
        """
        Create vector embeddings for the FMEA graph.

        Returns:
            bool: True if the vector embeddings were created successfully, False otherwise.
        """
        # Get all failure mode ids
        failureModeIds = self.get_failure_mode_ids()

        # Ensure the vector index exists and is ONLINE before adding embeddings.
        # This avoids Q&A failures like: "There is no such vector schema index: vector".
        self._ensure_vector_index()

        # Add the failure measures to the index
        for entry in failureModeIds:
            id = entry["ID(fd)"]
            nodes = self.traverse_graph(str(id)) # nodes是一个字典列表。每个字典代表 Neo4j 查询返回的“一行结果/一条记录
            chunk, nodeIds = self.create_chunk(nodes)
            # 对 chunk 做 embedding（把文本变成向量），并把文本+向量+元数据(nodeids)写进 Neo4j
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

    # 参数：nodes(list[dict])；返回：(chunk(str), nodeIds(dict))；功能：把遍历到的节点记录去重汇总后拼成一段可检索文本，并同时收集相关节点 ID 作为元数据。
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
            fm_node = node.get("fm")
            if fm_node is not None and fm_node not in fm:
                fm.append(fm_node)
                if node.get("ID(fm)") is not None:
                    nodeIds["failureMeasureIds"].append(node["ID(fm)"])

            fc_node = node.get("fc")
            if fc_node is not None and fc_node not in fc:
                fc.append(fc_node)
                if node.get("ID(fc)") is not None:
                    nodeIds["failureCauseIds"].append(node["ID(fc)"])

            fe_node = node.get("fe")
            if fe_node is not None and fe_node not in fe:
                fe.append(fe_node)
                if node.get("ID(fe)") is not None:
                    nodeIds["failureEffectIds"].append(node["ID(fe)"])

            fd_node = node.get("fd")
            if fd_node is not None and fd_node not in fd:
                fd.append(fd_node)
                if node.get("ID(fd)") is not None:
                    nodeIds["failureModeIds"].append(node["ID(fd)"])

            ps_node = node.get("ps")
            if ps_node is not None and ps_node not in ps:
                ps.append(ps_node)
                if node.get("ID(ps)") is not None:
                    nodeIds["processStepIds"].append(node["ID(ps)"])

        def _get_str(d: object, key: str) -> str:
            if not isinstance(d, dict):
                return ""
            v = d.get(key)
            if v is None:
                return ""
            return str(v)

        chunk = (
            ", ".join("ProcessStep: " + _get_str(i, "ProcessStep") for i in ps)
            + "".join(
                ", FailureMode: "
                + _get_str(i, "FailureMode")
                + ", RPN: "
                + _get_str(i, "RPN")
                for i in fd
            )
            + "".join(
                ", FailureEffect: "
                + _get_str(i, "FailureEffect")
                + ", S: "
                + _get_str(i, "S")
                for i in fe
            )
            + "".join(
                ", FailureCause: "
                + _get_str(i, "FailureCause")
                + ", O: "
                + _get_str(i, "O")
                for i in fc
            )
            + "".join(
                ", FailureMeasure: "
                + _get_str(i, "FailureMeasure")
                + ", DetectionMeasure: "
                + _get_str(i, "DetectionMeasure")
                + ", D: "
                + _get_str(i, "D")
                for i in fm
            )
        )

        return chunk, nodeIds

    @staticmethod
    def _normalize_process_step_name(name: str) -> str:
        s = (name or "").strip()
        # 常见问法会把“设计项目/项目/工序/过程步骤”等后缀带进实体里；图里通常只存核心名称。
        s = re.sub(r"(设计项目|过程步骤|工序|项目)$", "", s).strip()
        # 归一化空白
        s = re.sub(r"\s+", " ", s)
        return s

    @classmethod
    def _extract_process_step_from_question(cls, question: str) -> str | None:
        q = (question or "").strip()
        # 典型："动力电池设计项目对应的潜在的失效模式是什么"
        patterns = [
            r"^(?P<ps>.+?)(?:对应)?的?(?:潜在的)?失效模式(?:是|有哪些|有什么|是什么)?[？?]?$",
        ]
        for pat in patterns:
            m = re.match(pat, q)
            if not m:
                continue
            ps = m.groupdict().get("ps")
            ps = cls._normalize_process_step_name(ps or "")
            return ps or None
        return None

    @classmethod
    def _extract_process_step_general(cls, question: str) -> str | None:
        """Extract ProcessStep mention from a broader range of questions.

        Examples:
        - 动力电池设计项目对应的严重度的平均值是什么
        - 动力电池设计项目对应的平均严重度是什么
        - 动力电池的平均严重度是多少
        - 动力电池平均严重度是多少
        """
        q = (question or "").strip()
        if not q:
            return None

        # 优先按“对应”截断：X对应的...
        if "对应" in q:
            left = q.split("对应", 1)[0]
            ps = cls._normalize_process_step_name(left)
            return ps or None

        # 其次按“的平均”截断：X的平均...
        if "的平均" in q:
            left = q.split("的平均", 1)[0]
            ps = cls._normalize_process_step_name(left)
            return ps or None

        # 再其次：X平均...
        if "平均" in q:
            left = q.split("平均", 1)[0]
            ps = cls._normalize_process_step_name(left)
            return ps or None

        return None

    def _query_params(self, cypher: str, params: dict) -> list[dict]:
        try:
            return self.query(cypher, params=params)
        except TypeError:
            # 兼容 query 不支持 params 的实现：仅在本函数内部做小范围替换
            rendered = cypher
            for k, v in params.items():
                safe = str(v).replace("\\", "\\\\").replace("'", "\\'")
                rendered = rendered.replace("$" + k, "'" + safe + "'")
            return self.query(rendered)

    def _try_answer_failure_modes_by_process_step(self, question: str) -> dict | None:
        """Deterministic answer for: '<设计项目/工序> 对应的潜在失效模式是什么'.

        Why: LLM 生成 Cypher 容易因为实体不精确（如“动力电池设计项目” vs 图中“动力电池”）
        而回退到向量检索/高温度回答，导致把其他工序的失效模式/失效原因混入答案。
        """
        ps_key = self._extract_process_step_from_question(question)
        if not ps_key:
            return None

        matched_name = self._match_process_step_name(ps_key)
        if not matched_name:
            return None

        # 2) 直接查该 ProcessStep 下所有 FailureMode
        modes = self._query_params(
            """
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {ProcessStep: $step})
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY fd.FailureMode
            """,
            {"step": matched_name},
        )
        items = [str(r.get("FailureMode") or "").strip() for r in modes]
        items = [x for x in items if x]
        if not items:
            return None

        answer = f"{matched_name} 对应的潜在失效模式包括：" + "，".join(items)
        return {
            "answer": answer,
            "context": [f"ProcessStep={matched_name}"],
            "context_raw": items,
        }

    def _match_process_step_name(self, ps_key: str) -> str | None:
        """Find the best matching ProcessStep name in graph."""
        ps_key = self._normalize_process_step_name(ps_key or "")
        if not ps_key:
            return None

        rows = self._query_params(
            "MATCH (ps:ProcessStep {ProcessStep: $name}) RETURN ps.ProcessStep AS name LIMIT 1",
            {"name": ps_key},
        )
        matched_name = rows[0].get("name") if rows else None
        if matched_name:
            return str(matched_name).strip() or None

        candidates = self._query_params(
            """
            WITH $key AS key
            MATCH (ps:ProcessStep)
            WHERE ps.ProcessStep CONTAINS key OR key CONTAINS ps.ProcessStep
            RETURN ps.ProcessStep AS name
            ORDER BY size(ps.ProcessStep) DESC
            LIMIT 10
            """,
            {"key": ps_key},
        )
        if candidates:
            return str(candidates[0].get("name") or "").strip() or None
        return None

    @staticmethod
    def _extract_avg_metric_from_question(question: str) -> str | None:
        q = (question or "").strip()
        if "平均" not in q:
            return None
        # 常见指标同义词
        if "严重度" in q or re.search(r"\bS\b", q, re.IGNORECASE):
            return "S"
        if "频度" in q or "发生度" in q or re.search(r"\bO\b", q, re.IGNORECASE):
            return "O"
        if "探测度" in q or "检测度" in q or re.search(r"\bD\b", q, re.IGNORECASE):
            return "D"
        if "RPN" in q.upper():
            return "RPN"
        return None

    def _try_answer_avg_metric_by_process_step(self, question: str) -> dict | None:
        """Deterministic answer for: '<设计项目> 的平均严重度/平均频度/平均探测度/平均RPN'."""
        metric = self._extract_avg_metric_from_question(question)
        if not metric:
            return None

        ps_key = self._extract_process_step_general(question)
        if not ps_key:
            return None

        matched_name = self._match_process_step_name(ps_key)
        if not matched_name:
            return None

        # 优先用 FailureMode 自身的数值字段（建图时写入），这是“按工序”最稳的口径。
        rows = self._query_params(
            f"""
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {{ProcessStep: $step}})
            WITH fd
            WHERE fd.{metric} IS NOT NULL
            RETURN avg(toFloat(fd.{metric})) AS avg_val, count(fd) AS n
            """.strip(),
            {"step": matched_name},
        )
        avg_val = rows[0].get("avg_val") if rows else None
        n = int(rows[0].get("n", 0)) if rows else 0

        if avg_val is None or n == 0:
            # 兼容旧数据（FailureMode 上未写 S/O/D）：尝试从 FailureEffect/FailureCause/FailureMeasure 上取
            fallback_map = {
                "S": ("FailureEffect", "resultsInFailureEffect", "S"),
                "O": ("FailureCause", "isDueToFailureCause", "O"),
                "D": ("FailureMeasure", "isImprovedByFailureMeasure", "D"),
            }
            if metric in fallback_map:
                label, rel, prop = fallback_map[metric]
                frows = self._query_params(
                    f"""
                    MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {{ProcessStep: $step}})
                    MATCH (fd)-[:{rel}]->(x:{label})
                    WHERE x.{prop} IS NOT NULL
                    RETURN avg(toFloat(x.{prop})) AS avg_val, count(DISTINCT fd) AS n
                    """.strip(),
                    {"step": matched_name},
                )
                avg_val = frows[0].get("avg_val") if frows else None
                n = int(frows[0].get("n", 0)) if frows else 0

        if avg_val is None or n == 0:
            return None

        # 统一展示 2 位小数
        try:
            avg_num = float(avg_val)
        except Exception:
            return None

        metric_name = {
            "S": "严重度",
            "O": "频度数",
            "D": "探测度数",
            "RPN": "RPN",
        }.get(metric, metric)

        answer = f"{matched_name} 对应的{metric_name}平均值为 {avg_num:.2f}（n={n}）。"
        return {
            "answer": answer,
            "context": [f"ProcessStep={matched_name}", f"metric={metric}"],
            "context_raw": {"avg": avg_num, "n": n},
        }

    # ------------------------------
    # Global / cross-project deterministic answers
    # ------------------------------

    @staticmethod
    def _extract_two_quoted_names(question: str) -> tuple[str, str] | None:
        names = re.findall(r"“([^”]+)”", question or "")
        if len(names) >= 2:
            a = str(names[0]).strip()
            b = str(names[1]).strip()
            if a and b:
                return a, b
        return None

    def _try_answer_global_extreme_rpn(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "RPN" not in q.upper():
            return None
        if "失效模式" not in q:
            return None

        want_max = ("风险最高" in q) or ("最高" in q) or ("最大" in q)
        want_min = ("风险最低" in q) or ("最低" in q) or ("最小" in q)
        if not (want_max or want_min):
            return None

        agg_fn = "max" if want_max else "min"
        rows = self._query_params(
            f"""
            MATCH (fd:FailureMode)
            WHERE fd.RPN IS NOT NULL
            RETURN {agg_fn}(toFloat(fd.RPN)) AS extreme
            """.strip(),
            {},
        )
        extreme = rows[0].get("extreme") if rows else None
        if extreme is None:
            return None
        try:
            extreme_val = float(extreme)
        except Exception:
            return None

        rows2 = self._query_params(
            """
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
            WHERE fd.RPN IS NOT NULL AND toFloat(fd.RPN) = $v
            RETURN DISTINCT fd.FailureMode AS FailureMode, ps.ProcessStep AS ProcessStep
            ORDER BY ps.ProcessStep, fd.FailureMode
            """.strip(),
            {"v": extreme_val},
        )
        items: list[dict[str, object]] = []
        modes: list[str] = []
        for r in rows2:
            fm = str(r.get("FailureMode") or "").strip()
            ps = str(r.get("ProcessStep") or "").strip()
            if fm:
                modes.append(fm)
            if fm and ps:
                items.append({"FailureMode": fm, "ProcessStep": ps, "RPN": extreme_val})
        modes = sorted({m for m in modes if m})
        if not modes:
            return None

        word = "最高" if want_max else "最低"
        vtxt = str(int(extreme_val)) if float(extreme_val).is_integer() else str(extreme_val)
        answer = f"按RPN看，全局风险{word}值为 {vtxt}，对应失效模式：" + "，".join(modes)
        return {
            "answer": answer,
            "context": [f"metric=RPN", f"extreme={'max' if want_max else 'min'}", "scope=global"],
            "context_raw": {"value": extreme_val, "modes": modes, "rows": items},
        }

    def _try_answer_global_extreme_metric_modes(self, question: str) -> dict | None:
        """Deterministic answer for global extreme (max/min) of S/O/D/RPN on FailureMode.

        Examples:
        - 根据RPN数值，目前风险最高... 失效模式是什么（RPN max）
        - 频度数(O)最高的失效模式有哪些
        - 探测度(D)最高的失效模式有哪些
        """
        q = (question or "").strip()
        if not q:
            return None
        if "失效模式" not in q:
            return None
        # “平均X最高”类问题应走“项目均值对比”，不要误判为“单条极值”。
        if "平均" in q:
            return None

        metric = self._extract_metric_any(q)
        if not metric:
            return None

        want_max = any(k in q for k in ("风险最高", "最高", "最大"))
        want_min = any(k in q for k in ("风险最低", "最低", "最小"))
        if not (want_max or want_min):
            return None

        agg_fn = "max" if want_max else "min"
        rows = self._query_params(
            f"""
            MATCH (fd:FailureMode)
            WHERE fd.{metric} IS NOT NULL
            RETURN {agg_fn}(toFloat(fd.{metric})) AS extreme
            """.strip(),
            {},
        )
        extreme = rows[0].get("extreme") if rows else None
        if extreme is None:
            return None
        try:
            extreme_val = float(extreme)
        except Exception:
            return None

        rows2 = self._query_params(
            f"""
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
            WHERE fd.{metric} IS NOT NULL AND toFloat(fd.{metric}) = $v
            RETURN DISTINCT fd.FailureMode AS FailureMode, ps.ProcessStep AS ProcessStep
            ORDER BY ps.ProcessStep, fd.FailureMode
            """.strip(),
            {"v": extreme_val},
        )
        modes = sorted({str(r.get("FailureMode") or "").strip() for r in rows2 if str(r.get("FailureMode") or "").strip()})
        if not modes:
            return None

        metric_name = {"S": "严重度(S)", "O": "频度数(O)", "D": "探测度(D)", "RPN": "RPN"}.get(metric, metric)
        word = "最高" if want_max else "最低"
        vtxt = str(int(extreme_val)) if float(extreme_val).is_integer() else str(extreme_val)
        answer = f"按{metric_name}看，全局{word}值为 {vtxt}，对应失效模式：" + "，".join(modes)
        return {
            "answer": answer,
            "context": [f"metric={metric}", f"extreme={'max' if want_max else 'min'}", "scope=global"],
            "context_raw": {"value": extreme_val, "modes": modes},
        }

    def _try_answer_global_top_rpn_with_project(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "RPN排名前五" not in q and "RPN" not in q.upper():
            return None
        if "排名前五" not in q and "前五" not in q:
            return None
        if "失效模式" not in q:
            return None

        # 先取前 5 的“阈值”，再把与第 5 名并列的也一起返回，避免并列导致“第五名是谁”不唯一。
        top5 = self._query_params(
            """
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
            WHERE fd.RPN IS NOT NULL
            RETURN fd.FailureMode AS FailureMode, ps.ProcessStep AS ProcessStep, toFloat(fd.RPN) AS RPN
            ORDER BY RPN DESC
            LIMIT 5
            """.strip(),
            {},
        )
        if not top5:
            return None
        try:
            cutoff = min(float(r.get("RPN")) for r in top5 if r.get("RPN") is not None)
        except Exception:
            return None

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
            WHERE fd.RPN IS NOT NULL AND toFloat(fd.RPN) >= $cutoff
            RETURN fd.FailureMode AS FailureMode, ps.ProcessStep AS ProcessStep, toFloat(fd.RPN) AS RPN
            ORDER BY RPN DESC, ps.ProcessStep ASC, fd.FailureMode ASC
            """.strip(),
            {"cutoff": cutoff},
        )

        items: list[dict[str, object]] = []
        parts: list[str] = []
        for i, r in enumerate(rows, start=1):
            fm = str(r.get("FailureMode") or "").strip()
            ps = str(r.get("ProcessStep") or "").strip()
            v = r.get("RPN")
            if not fm or v is None:
                continue
            try:
                vv = float(v)
            except Exception:
                continue
            items.append({"FailureMode": fm, "ProcessStep": ps, "RPN": vv})
            vtxt = str(int(vv)) if float(vv).is_integer() else str(vv)
            parts.append(f"{i}) {fm}（项目：{ps}，RPN={vtxt}）")

        if not items:
            return None
        answer = "RPN 排名前五（含并列）的失效模式如下：" + "；".join(parts)
        return {
            "answer": answer,
            "context": ["metric=RPN", "top=5+tied", "scope=global"],
            "context_raw": items,
        }

    def _try_answer_global_rpn_threshold_list(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "RPN" not in q.upper() or "失效模式" not in q:
            return None

        m = re.search(r"RPN\s*值?\s*(超过|高于|大于|低于|小于)\s*(\d+(?:\.\d+)?)", q)
        if not m:
            return None
        op = m.group(1)
        thr = float(m.group(2))
        want_gt = op in ("超过", "高于", "大于")

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.RPN IS NOT NULL
            WITH fd, toFloat(fd.RPN) AS v
            WHERE (v > $thr AND $want_gt = true) OR (v < $thr AND $want_gt = false)
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY fd.FailureMode
            """.strip(),
            {"thr": thr, "want_gt": want_gt},
        )
        items = [str(r.get("FailureMode") or "").strip() for r in rows]
        items = [x for x in items if x]
        if not items:
            return None

        word = "超过" if want_gt else "低于"
        ttxt = str(int(thr)) if float(thr).is_integer() else str(thr)
        answer = f"所有 RPN 值{word} {ttxt} 的失效模式如下：" + "，".join(items)
        return {
            "answer": answer,
            "context": ["metric=RPN", f"threshold={word}{ttxt}", "scope=global"],
            "context_raw": items,
        }

    def _try_answer_project_max_avg_metric(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "哪个" not in q or "设计项目" not in q or "平均" not in q or "最高" not in q:
            return None
        metric = self._extract_avg_metric_from_question(q)
        if not metric:
            return None

        rows = self._query_params(
            f"""
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
            WHERE fd.{metric} IS NOT NULL
            WITH ps.ProcessStep AS ProcessStep, avg(toFloat(fd.{metric})) AS avg_val, count(fd) AS n
            RETURN ProcessStep, avg_val, n
            ORDER BY avg_val DESC, n DESC, ProcessStep ASC
            LIMIT 1
            """.strip(),
            {},
        )
        if not rows:
            return None
        ps = str(rows[0].get("ProcessStep") or "").strip()
        avg_val = rows[0].get("avg_val")
        n = int(rows[0].get("n", 0) or 0)
        if not ps or avg_val is None or n <= 0:
            return None
        try:
            av = float(avg_val)
        except Exception:
            return None

        metric_name = {"S": "严重度(S)", "O": "频度数(O)", "D": "探测度(D)", "RPN": "RPN"}.get(metric, metric)
        answer = f"平均{metric_name}最高的设计项目是：{ps}（平均值={av:.2f}，n={n}）。"
        return {
            "answer": answer,
            "context": ["scope=global", f"metric={metric}", "agg=avg", "argmax=1"],
            "context_raw": {"ProcessStep": ps, "avg": av, "n": n},
        }

    def _try_answer_compare_two_projects_avg_rpn(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "比较" not in q or "平均RPN" not in q:
            return None
        names = self._extract_two_quoted_names(q)
        if not names:
            return None
        a, b = names

        rows = self._query_params(
            """
            UNWIND $steps AS step
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {ProcessStep: step})
            WHERE fd.RPN IS NOT NULL
            RETURN step AS ProcessStep, avg(toFloat(fd.RPN)) AS avg_val, count(fd) AS n
            """.strip(),
            {"steps": [a, b]},
        )
        mp = {str(r.get("ProcessStep") or "").strip(): r for r in rows or []}
        if a not in mp or b not in mp:
            return None
        try:
            av_a = float(mp[a].get("avg_val"))
            av_b = float(mp[b].get("avg_val"))
        except Exception:
            return None
        winner = a if av_a >= av_b else b
        answer = f"{a} 的平均RPN为 {av_a:.2f}；{b} 的平均RPN为 {av_b:.2f}。平均RPN更高的是：{winner}。"
        return {
            "answer": answer,
            "context": ["scope=global", "metric=RPN", "compare=2"],
            "context_raw": {a: av_a, b: av_b, "winner": winner},
        }

    def _try_answer_modes_by_severity(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q or "严重度" not in q or "失效模式" not in q:
            return None
        m = re.search(r"严重度\s*\(?S\)?\s*为\s*(\d+)\s*分?", q)
        if not m:
            return None
        sev = int(m.group(1))
        if sev < 0 or sev > 10:
            return None
        rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.S IS NOT NULL AND toInteger(toFloat(fd.S)) = $s
            RETURN DISTINCT fd.FailureMode AS FailureMode, toFloat(fd.RPN) AS RPN
            ORDER BY fd.FailureMode
            """.strip(),
            {"s": sev},
        )
        modes: list[str] = []
        rpns: list[float] = []
        for r in rows:
            fm = str(r.get("FailureMode") or "").strip()
            if fm:
                modes.append(fm)
            v = r.get("RPN")
            if v is not None:
                try:
                    rpns.append(float(v))
                except Exception:
                    pass
        modes = [x for x in modes if x]
        if not modes:
            return None
        dist = ""
        if rpns:
            dist = f"RPN分布：min={min(rpns):.0f}，max={max(rpns):.0f}，avg={sum(rpns)/len(rpns):.2f}"  # noqa: E501
        answer = f"严重度(S)={sev} 的失效模式共有 {len(modes)} 项：" + "，".join(modes)
        if dist:
            answer += "。" + dist + "。"
        return {
            "answer": answer,
            "context": ["scope=global", f"S={sev}"],
            "context_raw": {"S": sev, "modes": modes, "rpn_values": rpns},
        }

    def _try_answer_effects_and_modes_by_severity(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "严重度" not in q or "失效后果" not in q:
            return None
        m = re.search(r"严重度\s*\(?S\)?\s*为\s*(\d+)\s*分?", q)
        if not m:
            return None
        sev = int(m.group(1))
        if sev < 0 or sev > 10:
            return None

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:resultsInFailureEffect]->(fe:FailureEffect)
            WHERE fd.S IS NOT NULL AND toInteger(toFloat(fd.S)) = $s
            RETURN fe.FailureEffect AS FailureEffect, collect(DISTINCT fd.FailureMode) AS Modes
            ORDER BY fe.FailureEffect
            """.strip(),
            {"s": sev},
        )
        items: list[dict[str, object]] = []
        all_modes: list[str] = []
        parts: list[str] = []
        for r in rows:
            eff = str(r.get("FailureEffect") or "").strip()
            modes = [str(x).strip() for x in (r.get("Modes") or []) if str(x).strip()]
            if not eff and not modes:
                continue
            if modes:
                all_modes.extend(modes)
            items.append({"FailureEffect": eff, "FailureModes": sorted(set(modes))})
            if eff:
                modes_txt = "，".join(sorted(set(modes))) if modes else "（无）"
                parts.append(f"{eff} ← {modes_txt}")

        all_modes = sorted(set(all_modes))
        if not items and not all_modes:
            return None

        if parts:
            answer = f"严重度(S)={sev} 的失效后果及其对应失效模式如下：" + "；".join(parts)
        else:
            answer = f"严重度(S)={sev} 的对应失效模式：" + "，".join(all_modes)
        return {
            "answer": answer,
            "context": ["scope=global", f"S={sev}", "effects=1"],
            "context_raw": {"S": sev, "items": items, "modes": all_modes},
        }

    def _try_answer_modes_by_effect_double_contains(self, question: str) -> dict | None:
        """Deterministic answer for: '哪些失效模式的后果描述中同时包含A和B'.

        规则：严格按字面匹配（Cypher CONTAINS），不做同义词扩展；即使 0 命中也要直接返回“无”，
        避免落入 LLM/RAG 语义推断导致偏离题意。
        """

        q = (question or "").strip()
        if not q:
            return None

        if "失效模式" not in q:
            return None
        if not ("后果" in q or "失效后果" in q or "后果描述" in q):
            return None
        if not ("同时包含" in q or "同时含有" in q or "同时包括" in q or "同时包含了" in q):
            return None

        # 1) 优先提取引号中的关键词（支持中英文引号）
        quoted = re.findall(r"[“\"‘']([^”\"’']+)[”\"’']", q)
        quoted = [str(x).strip() for x in quoted if str(x).strip()]

        kw1 = ""
        kw2 = ""
        if len(quoted) >= 2:
            kw1, kw2 = quoted[0], quoted[1]
        elif len(quoted) == 1:
            kw1 = quoted[0]
            # 尝试从“kw1 和 <kw2>”结构中抽取第二个关键词（到常见标点为止）
            m = re.search(
                re.escape(kw1) + r".*?(?:和|以及|及|与)\s*([^？\?。；;，,]+)",
                q,
            )
            if m:
                kw2 = str(m.group(1)).strip()
            else:
                # 退化：直接取“和/以及/及/与”后的片段
                m2 = re.search(r"(?:和|以及|及|与)\s*([^？\?。；;，,]+)", q)
                if m2:
                    kw2 = str(m2.group(1)).strip()
        else:
            # 没有引号时，尽量从“同时包含A和B”里抽取
            m = re.search(r"同时包含(?:了)?\s*([^和以及及与]+)\s*(?:和|以及|及|与)\s*([^？\?。；;，,]+)", q)
            if m:
                kw1 = str(m.group(1)).strip()
                kw2 = str(m.group(2)).strip()

        if not kw1 or not kw2:
            return None

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:resultsInFailureEffect]->(fe:FailureEffect)
            WHERE fe.FailureEffect CONTAINS $kw1
              AND fe.FailureEffect CONTAINS $kw2
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY FailureMode
            """.strip(),
            {"kw1": kw1, "kw2": kw2},
        )
        items = [str(r.get("FailureMode") or "").strip() for r in rows]
        items = [x for x in items if x]

        if items:
            answer = f"后果描述同时包含“{kw1}”和“{kw2}”的失效模式包括：" + "，".join(items)
        else:
            answer = f"后果描述中同时包含“{kw1}”和“{kw2}”的失效模式：无。"

        return {
            "answer": answer,
            "context": ["scope=global", f"effect_contains={kw1}&{kw2}", "list=modes"],
            "context_raw": {"kw1": kw1, "kw2": kw2, "modes": items, "count": len(items)},
        }

    def _try_answer_count_modes_by_effect_keyword(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q or "后果" not in q or "总共有多少" not in q or "失效模式" not in q:
            return None
        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None
        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:resultsInFailureEffect]->(fe:FailureEffect)
            WHERE fe.FailureEffect CONTAINS $kw
            RETURN count(DISTINCT fd) AS c
            """.strip(),
            {"kw": kw},
        )
        c = int(rows[0].get("c", 0) or 0) if rows else 0
        answer = f"后果包含“{kw}”的失效模式共有 {c} 项。"
        return {
            "answer": answer,
            "context": ["scope=global", f"effect_kw={kw}", "agg=count"],
            "context_raw": {"keyword": kw, "count": c},
        }

    def _try_answer_projects_by_effect_keyword(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q or "后果为" not in q or "集中" not in q or "设计项目" not in q:
            return None
        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None
        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:resultsInFailureEffect]->(fe:FailureEffect)
            MATCH (fd)-[:occursAtProcessStep]->(ps:ProcessStep)
            WHERE fe.FailureEffect CONTAINS $kw
            RETURN DISTINCT ps.ProcessStep AS ProcessStep
            ORDER BY ProcessStep
            """.strip(),
            {"kw": kw},
        )
        items = [str(r.get("ProcessStep") or "").strip() for r in rows]
        items = [x for x in items if x]
        if not items:
            return None
        answer = f"后果包含“{kw}”的失效模式主要分布在这些设计项目：" + "，".join(items)
        return {
            "answer": answer,
            "context": ["scope=global", f"effect_kw={kw}", "list=projects"],
            "context_raw": items,
        }

    def _try_answer_modes_by_control_keyword(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None

        # detect control -> modes
        if ("用于探测" in q or "被用于探测" in q or "用于检测" in q) and "失效模式" in q:
            # Prefer newer graphs: DetectionMeasure on FailureMode
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.DetectionMeasure IS NOT NULL
                  AND trim(toString(fd.DetectionMeasure)) <> ''
                  AND toString(fd.DetectionMeasure) CONTAINS $kw
                RETURN DISTINCT fd.FailureMode AS FailureMode
                ORDER BY FailureMode
                """.strip(),
                {"kw": kw},
            )
            # Fallback: older graphs stored measures on FailureMeasure
            if not rows:
                rows = self._query_params(
                    """
                    MATCH (fd:FailureMode)-[:isDueToFailureCause]->(:FailureCause)-[:isImprovedByFailureMeasure]->(fm:FailureMeasure)
                    WHERE (fm.DetectionMeasure IS NOT NULL AND toString(fm.DetectionMeasure) CONTAINS $kw)
                       OR (fm.FailureMeasure IS NOT NULL AND toString(fm.FailureMeasure) CONTAINS $kw)
                    RETURN DISTINCT fd.FailureMode AS FailureMode
                    ORDER BY FailureMode
                    """.strip(),
                    {"kw": kw},
                )
            items = [str(r.get("FailureMode") or "").strip() for r in rows]
            items = [x for x in items if x]
            if not items:
                return None
            answer = f"探测性控制“{kw}”用于探测的失效模式包括：" + "，".join(items)
            return {
                "answer": answer,
                "context": ["scope=global", f"ctrl={kw}", "list=modes"],
                "context_raw": items,
            }

        # control -> projects
        if "主要应用于哪些设计项目" in q:
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
                WHERE (
                    (fd.DetectionMeasure IS NOT NULL AND trim(toString(fd.DetectionMeasure)) <> '' AND toString(fd.DetectionMeasure) CONTAINS $kw)
                 OR (fd.PreventControl IS NOT NULL AND trim(toString(fd.PreventControl)) <> '' AND toString(fd.PreventControl) CONTAINS $kw)
                 OR (fd.TempMeasure IS NOT NULL AND trim(toString(fd.TempMeasure)) <> '' AND toString(fd.TempMeasure) CONTAINS $kw)
                )
                RETURN DISTINCT ps.ProcessStep AS ProcessStep
                ORDER BY ProcessStep
                """.strip(),
                {"kw": kw},
            )
            if not rows:
                rows = self._query_params(
                    """
                    MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
                    OPTIONAL MATCH (fd)-[:isDueToFailureCause]->(:FailureCause)-[:isImprovedByFailureMeasure]->(fm:FailureMeasure)
                    WHERE (fm.DetectionMeasure IS NOT NULL AND toString(fm.DetectionMeasure) CONTAINS $kw)
                       OR (fm.FailureMeasure IS NOT NULL AND toString(fm.FailureMeasure) CONTAINS $kw)
                    RETURN DISTINCT ps.ProcessStep AS ProcessStep
                    ORDER BY ProcessStep
                    """.strip(),
                    {"kw": kw},
                )
            items = [str(r.get("ProcessStep") or "").strip() for r in rows]
            items = [x for x in items if x]
            if not items:
                return None
            answer = f"“{kw}”主要应用于这些设计项目：" + "，".join(items)
            return {
                "answer": answer,
                "context": ["scope=global", f"ctrl={kw}", "list=projects"],
                "context_raw": items,
            }

        # prevent control -> modes
        if "这一预防措施" in q and "主要防止哪些失效" in q:
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.PreventControl IS NOT NULL
                  AND trim(toString(fd.PreventControl)) <> ''
                  AND toString(fd.PreventControl) CONTAINS $kw
                RETURN DISTINCT fd.FailureMode AS FailureMode
                ORDER BY FailureMode
                """.strip(),
                {"kw": kw},
            )
            if not rows:
                rows = self._query_params(
                    """
                    MATCH (fd:FailureMode)-[:isDueToFailureCause]->(:FailureCause)-[:isImprovedByFailureMeasure]->(fm:FailureMeasure)
                    WHERE fm.FailureMeasure IS NOT NULL AND toString(fm.FailureMeasure) CONTAINS $kw
                    RETURN DISTINCT fd.FailureMode AS FailureMode
                    ORDER BY FailureMode
                    """.strip(),
                    {"kw": kw},
                )
            items = [str(r.get("FailureMode") or "").strip() for r in rows]
            items = [x for x in items if x]
            if not items:
                return None
            answer = f"预防性控制“{kw}”主要涉及/预防的失效模式包括：" + "，".join(items)
            return {
                "answer": answer,
                "context": ["scope=global", f"prevent_kw={kw}", "list=modes"],
                "context_raw": items,
            }

        return None

    def _try_answer_control_category_by_keyword(self, question: str) -> dict | None:
        """Deterministic answer for: '“X”是预防措施还是探测措施？或是临时措施？'."""

        q = (question or "").strip()
        if not q:
            return None
        if "是预防措施还是探测措施" not in q:
            return None
        if "临时措施" not in q:
            return None

        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            RETURN
              sum(CASE WHEN fd.PreventControl IS NOT NULL AND trim(toString(fd.PreventControl)) <> '' AND toString(fd.PreventControl) CONTAINS $kw THEN 1 ELSE 0 END) AS cPrev,
              sum(CASE WHEN fd.DetectionMeasure IS NOT NULL AND trim(toString(fd.DetectionMeasure)) <> '' AND toString(fd.DetectionMeasure) CONTAINS $kw THEN 1 ELSE 0 END) AS cDet,
              sum(CASE WHEN fd.TempMeasure IS NOT NULL AND trim(toString(fd.TempMeasure)) <> '' AND toString(fd.TempMeasure) CONTAINS $kw THEN 1 ELSE 0 END) AS cTemp
            """.strip(),
            {"kw": kw},
        )
        c_prev = int(rows[0].get("cPrev", 0) or 0) if rows else 0
        c_det = int(rows[0].get("cDet", 0) or 0) if rows else 0
        c_temp = int(rows[0].get("cTemp", 0) or 0) if rows else 0

        # Fallback for older graphs if nothing is found in dedicated fields.
        if c_prev == 0 and c_det == 0 and c_temp == 0:
            rows2 = self._query_params(
                """
                MATCH (fm:FailureMeasure)
                WHERE (fm.DetectionMeasure IS NOT NULL AND trim(toString(fm.DetectionMeasure)) <> '' AND toString(fm.DetectionMeasure) CONTAINS $kw)
                   OR (fm.FailureMeasure IS NOT NULL AND trim(toString(fm.FailureMeasure)) <> '' AND toString(fm.FailureMeasure) CONTAINS $kw)
                RETURN DISTINCT toString(fm.FailureMeasure) AS FailureMeasure,
                                toString(fm.DetectionMeasure) AS DetectionMeasure
                LIMIT 200
                """.strip(),
                {"kw": kw},
            )

            has_det = False
            has_prev = False
            has_temp = False

            for r in rows2:
                det = str(r.get("DetectionMeasure") or "").strip()
                if det and det.lower() != "nan" and kw in det:
                    has_det = True

                blob = str(r.get("FailureMeasure") or "").strip()
                if not blob:
                    continue
                m_prev = re.search(r"预防控制：([^；]+)", blob)
                if m_prev and kw in m_prev.group(1):
                    has_prev = True
                m_temp = re.search(r"临时/改进措施：(.+)$", blob)
                if m_temp and kw in m_temp.group(1):
                    has_temp = True
                # tolerate other legacy labels
                if "临时措施：" in blob and kw in blob:
                    has_temp = True
                if "探测控制：" in blob and kw in blob:
                    has_det = True

            labels: list[str] = []
            if has_prev:
                labels.append("预防措施")
            if has_det:
                labels.append("探测措施")
            if has_temp:
                labels.append("临时措施")
            if not labels:
                return None
            if len(labels) == 1:
                answer = f"“{kw}”在文档中属于{labels[0]}。"
            else:
                answer = f"“{kw}”在文档中同时出现在：" + "、".join(labels) + "。"
            return {
                "answer": answer,
                "context": ["scope=global", f"kw={kw}", "legacy_graph"],
                "context_raw": {"prevent": has_prev, "detect": has_det, "temp": has_temp},
            }

        labels: list[str] = []
        if c_prev > 0:
            labels.append("预防措施")
        if c_det > 0:
            labels.append("探测措施")
        if c_temp > 0:
            labels.append("临时措施")

        if not labels:
            return None

        if len(labels) == 1:
            answer = f"“{kw}”在文档中属于{labels[0]}。"
        else:
            answer = f"“{kw}”在文档中同时出现在：" + "、".join(labels) + "。"

        return {
            "answer": answer,
            "context": ["scope=global", f"kw={kw}", f"cPrev={c_prev}", f"cDet={c_det}", f"cTemp={c_temp}"],
            "context_raw": {"cPrev": c_prev, "cDet": c_det, "cTemp": c_temp},
        }

    def _try_answer_controls_by_failure_mode(self, question: str) -> dict | None:
        """Deterministic answer for: given a (quoted) failure mode, return its preventive/detective controls."""

        q = (question or "").strip()
        if not q:
            return None

        is_detect = "探测性控制" in q or "探测性设计控制" in q
        is_prevent = "预防性" in q and "设计控制" in q
        if not (is_detect or is_prevent):
            return None
        if "现行" not in q or "是什么" not in q:
            return None

        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None

        # First, confirm the failure mode exists (avoid hijacking when user quotes unrelated text).
        rows_modes = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.FailureMode IS NOT NULL AND toString(fd.FailureMode) CONTAINS $kw
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY FailureMode
            LIMIT 5
            """.strip(),
            {"kw": kw},
        )
        matched_modes = [str(r.get("FailureMode") or "").strip() for r in rows_modes]
        matched_modes = [x for x in matched_modes if x]
        if not matched_modes:
            return None

        mode_label = matched_modes[0] if len(matched_modes) == 1 else kw

        if is_detect:
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.FailureMode IS NOT NULL AND toString(fd.FailureMode) CONTAINS $kw
                RETURN DISTINCT toString(fd.DetectionMeasure) AS v
                """.strip(),
                {"kw": kw},
            )
            items = [str(r.get("v") or "").strip() for r in rows]
            items = [x for x in items if x and x.lower() != "nan"]
            if not items:
                # NOTE: Do NOT fall back to the legacy graph path (FailureCause->FailureMeasure),
                # because measures are attached to causes and may be shared across multiple modes,
                # leading to cross-mode contamination.
                schema_rows = self._query_params(
                    """
                    MATCH (fd:FailureMode)
                    WHERE fd.PreventControl IS NOT NULL
                       OR fd.DetectionMeasure IS NOT NULL
                       OR fd.TempMeasure IS NOT NULL
                    RETURN count(fd) AS c
                    """.strip(),
                    {},
                )
                has_mode_controls = bool(schema_rows) and int(schema_rows[0].get("c", 0) or 0) > 0

                # Safe fallback for legacy graphs: read from default dfmea_final.csv (row-level truth).
                used_csv_fallback = False
                if not has_mode_controls:
                    df = self._get_default_dfmea_df()
                    if df is not None and {"FailureMode", "DetectionMeasure"}.issubset(set(df.columns)):
                        m = df["FailureMode"].astype(str).str.contains(kw, na=False)
                        vals = df.loc[m, "DetectionMeasure"].fillna("").astype(str).str.strip().tolist()
                        vals = [v for v in vals if v and v.lower() != "nan"]
                        if vals:
                            used_csv_fallback = True
                            items = vals

                if items:
                    answer = f"针对“{mode_label}”，现行探测性设计控制包括：" + "，".join(sorted(set(items))) + "。"
                    return {
                        "answer": answer,
                        "context": [
                            "scope=global",
                            f"mode_kw={kw}",
                            "control=detect",
                            f"csv_fallback={str(used_csv_fallback).lower()}",
                        ],
                        "context_raw": items,
                    }
                answer = f"针对“{mode_label}”，文档中未记录现行探测性设计控制。"
                return {
                    "answer": answer,
                    "context": [
                        "scope=global",
                        f"mode_kw={kw}",
                        "control=detect",
                        "controls=none",
                        f"legacy_graph_no_mode_controls={str(not has_mode_controls).lower()}",
                        "csv_fallback=false",
                    ],
                    "context_raw": {"matched_modes": matched_modes, "controls": []},
                }

            answer = f"针对“{mode_label}”，现行探测性设计控制包括：" + "，".join(sorted(set(items))) + "。"
            return {
                "answer": answer,
                "context": ["scope=global", f"mode_kw={kw}", "control=detect"],
                "context_raw": items,
            }

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.FailureMode IS NOT NULL AND toString(fd.FailureMode) CONTAINS $kw
            RETURN DISTINCT toString(fd.PreventControl) AS v
            """.strip(),
            {"kw": kw},
        )
        items = [str(r.get("v") or "").strip() for r in rows]
        items = [x for x in items if x and x.lower() != "nan"]
        if not items:
            # Same reasoning as above: do not use FailureCause->FailureMeasure for mode-level controls.
            schema_rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.PreventControl IS NOT NULL
                   OR fd.DetectionMeasure IS NOT NULL
                   OR fd.TempMeasure IS NOT NULL
                RETURN count(fd) AS c
                """.strip(),
                {},
            )
            has_mode_controls = bool(schema_rows) and int(schema_rows[0].get("c", 0) or 0) > 0

            used_csv_fallback = False
            if not has_mode_controls:
                df = self._get_default_dfmea_df()
                if df is not None and {"FailureMode", "PreventControl"}.issubset(set(df.columns)):
                    m = df["FailureMode"].astype(str).str.contains(kw, na=False)
                    vals = df.loc[m, "PreventControl"].fillna("").astype(str).str.strip().tolist()
                    vals = [v for v in vals if v and v.lower() != "nan"]
                    if vals:
                        used_csv_fallback = True
                        items = vals

            if items:
                answer = f"针对“{mode_label}”，现行预防性设计控制包括：" + "，".join(sorted(set(items))) + "。"
                return {
                    "answer": answer,
                    "context": [
                        "scope=global",
                        f"mode_kw={kw}",
                        "control=prevent",
                        f"csv_fallback={str(used_csv_fallback).lower()}",
                    ],
                    "context_raw": items,
                }
            answer = f"针对“{mode_label}”，文档中未记录现行预防性设计控制。"
            return {
                "answer": answer,
                "context": [
                    "scope=global",
                    f"mode_kw={kw}",
                    "control=prevent",
                    "controls=none",
                    f"legacy_graph_no_mode_controls={str(not has_mode_controls).lower()}",
                    "csv_fallback=false",
                ],
                "context_raw": {"matched_modes": matched_modes, "controls": []},
            }

        answer = f"针对“{mode_label}”，现行预防性设计控制包括：" + "，".join(sorted(set(items))) + "。"
        return {
            "answer": answer,
            "context": ["scope=global", f"mode_kw={kw}", "control=prevent"],
            "context_raw": items,
        }

    def _try_answer_control_preference_by_project(self, question: str) -> dict | None:
        """Deterministic answer for: for a quoted project, whether it relies more on prevent or detect controls."""

        q = (question or "").strip()
        if not q:
            return None
        if "主要依赖" not in q or "控制手段" not in q:
            return None
        if "预防" not in q or "探测" not in q:
            return None

        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        proj = str(kws[0]).strip()
        if not proj:
            return None

        rows = self._query_params(
            """
            MATCH (ps:ProcessStep)
            WHERE ps.ProcessStep IS NOT NULL AND toString(ps.ProcessStep) CONTAINS $proj
            MATCH (ps)<-[:occursAtProcessStep]-(fd:FailureMode)
            WITH
              sum(CASE WHEN fd.PreventControl IS NOT NULL AND trim(toString(fd.PreventControl)) <> '' THEN 1 ELSE 0 END) AS cPrev,
              sum(CASE WHEN fd.DetectionMeasure IS NOT NULL AND trim(toString(fd.DetectionMeasure)) <> '' THEN 1 ELSE 0 END) AS cDet,
              count(fd) AS total
            RETURN cPrev, cDet, total
            """.strip(),
            {"proj": proj},
        )
        if not rows:
            return None

        c_prev = int(rows[0].get("cPrev", 0) or 0)
        c_det = int(rows[0].get("cDet", 0) or 0)
        total = int(rows[0].get("total", 0) or 0)
        if total <= 0:
            return None

        used_csv_fallback = False
        if c_prev == 0 and c_det == 0:
            schema_rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.PreventControl IS NOT NULL
                   OR fd.DetectionMeasure IS NOT NULL
                   OR fd.TempMeasure IS NOT NULL
                RETURN count(fd) AS c
                """.strip(),
                {},
            )
            has_mode_controls = bool(schema_rows) and int(schema_rows[0].get("c", 0) or 0) > 0
            if not has_mode_controls:
                df = self._get_default_dfmea_df()
                if df is not None and {"ProcessStep", "FailureMode"}.issubset(set(df.columns)):
                    m = df["ProcessStep"].astype(str).str.contains(proj, na=False)
                    sub = df.loc[m].copy()
                    sub = sub[sub["FailureMode"].notna()]
                    total2 = int(sub.shape[0])
                    if total2 > 0:
                        used_csv_fallback = True
                        total = total2
                        if "PreventControl" in sub.columns:
                            c_prev = int((sub["PreventControl"].fillna("").astype(str).str.strip() != "").sum())
                        if "DetectionMeasure" in sub.columns:
                            c_det = int((sub["DetectionMeasure"].fillna("").astype(str).str.strip() != "").sum())

        if c_prev > c_det:
            pref = "预防"
        elif c_det > c_prev:
            pref = "探测"
        else:
            pref = "预防与探测并重"

        if c_prev == 0 and c_det == 0:
            pref = "（预防/探测字段均未记录）"
        answer = f"从文档记录看，“{proj}”相关失效模式更偏向依赖：{pref}（预防={c_prev}，探测={c_det}，总失效模式={total}）。"
        return {
            "answer": answer,
            "context": ["scope=project", f"project_kw={proj}", "control=prefer", f"csv_fallback={str(used_csv_fallback).lower()}"],
            "context_raw": {"prevent": c_prev, "detect": c_det, "total": total},
        }

    def _try_answer_modes_by_control_presence(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "失效模式" not in q or "预防" not in q or "探测" not in q:
            return None

        # IMPORTANT: Do not fall back to FailureCause->FailureMeasure here.
        # In legacy graphs, measures are attached to causes and may be shared across modes,
        # which makes per-mode prevent/detect presence statistics unreliable.
        schema_rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.PreventControl IS NOT NULL
               OR fd.DetectionMeasure IS NOT NULL
               OR fd.TempMeasure IS NOT NULL
            RETURN count(fd) AS c
            """.strip(),
            {},
        )
        has_mode_controls = bool(schema_rows) and int(schema_rows[0].get("c", 0) or 0) > 0

        def _rows_to_items(rows: list[dict]) -> list[str]:
            items = [str(r.get("FailureMode") or "").strip() for r in rows]
            return [x for x in items if x]

        def _legacy_message(tag: str) -> dict:
            return {
                "answer": "当前知识图谱未写入失效模式级别的预防/探测字段，无法可靠统计（建议清空后重新导入 CSV 建图）。",
                "context": ["scope=global", f"controls={tag}", "legacy_graph_no_mode_controls=true"],
                "context_raw": {"modes": []},
            }

        # both prevent + detect
        if "同时" in q and ("配备" in q or "具备" in q):
            if not has_mode_controls:
                df = self._get_default_dfmea_df()
                if df is None or "FailureMode" not in df.columns:
                    return _legacy_message("both")
                pc = df["PreventControl"].fillna("").astype(str).str.strip() if "PreventControl" in df.columns else pd.Series([""] * len(df))
                dc = df["DetectionMeasure"].fillna("").astype(str).str.strip() if "DetectionMeasure" in df.columns else pd.Series([""] * len(df))
                m = (pc != "") & (dc != "")
                items = sorted({str(x).strip() for x in df.loc[m, "FailureMode"].tolist() if str(x).strip() and str(x).lower() != "nan"})
                if not items:
                    return _legacy_message("both")
                answer = "同时配备预防性与探测性控制的失效模式包括：" + "，".join(items)
                return {
                    "answer": answer,
                    "context": ["scope=global", "controls=both", "list=modes", "csv_fallback=true"],
                    "context_raw": items,
                }
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.PreventControl IS NOT NULL AND trim(toString(fd.PreventControl)) <> ''
                  AND fd.DetectionMeasure IS NOT NULL AND trim(toString(fd.DetectionMeasure)) <> ''
                RETURN DISTINCT fd.FailureMode AS FailureMode
                ORDER BY FailureMode
                """.strip(),
                {},
            )
            items = _rows_to_items(rows)
            if not items:
                return None
            answer = "同时配备预防性与探测性控制的失效模式包括：" + "，".join(items)
            return {"answer": answer, "context": ["scope=global", "controls=both", "list=modes"], "context_raw": items}

        # only prevent
        if "只有预防" in q and "没有探测" in q:
            if not has_mode_controls:
                df = self._get_default_dfmea_df()
                if df is None or "FailureMode" not in df.columns:
                    return _legacy_message("prevent_only")
                pc = df["PreventControl"].fillna("").astype(str).str.strip() if "PreventControl" in df.columns else pd.Series([""] * len(df))
                dc = df["DetectionMeasure"].fillna("").astype(str).str.strip() if "DetectionMeasure" in df.columns else pd.Series([""] * len(df))
                m = (pc != "") & (dc == "")
                items = sorted({str(x).strip() for x in df.loc[m, "FailureMode"].tolist() if str(x).strip() and str(x).lower() != "nan"})
                if not items:
                    return _legacy_message("prevent_only")
                answer = "只有预防性控制、没有探测性控制的失效模式包括：" + "，".join(items)
                return {
                    "answer": answer,
                    "context": ["scope=global", "controls=prevent_only", "list=modes", "csv_fallback=true"],
                    "context_raw": items,
                }
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.PreventControl IS NOT NULL AND trim(toString(fd.PreventControl)) <> ''
                  AND (fd.DetectionMeasure IS NULL OR trim(toString(fd.DetectionMeasure)) = '')
                RETURN DISTINCT fd.FailureMode AS FailureMode
                ORDER BY FailureMode
                """.strip(),
                {},
            )
            items = _rows_to_items(rows)
            if not items:
                return None
            answer = "只有预防性控制、没有探测性控制的失效模式包括：" + "，".join(items)
            return {
                "answer": answer,
                "context": ["scope=global", "controls=prevent_only", "list=modes"],
                "context_raw": items,
            }

        # only detect
        if "只有探测" in q and "没有预防" in q:
            if not has_mode_controls:
                df = self._get_default_dfmea_df()
                if df is None or "FailureMode" not in df.columns:
                    return _legacy_message("detect_only")
                pc = df["PreventControl"].fillna("").astype(str).str.strip() if "PreventControl" in df.columns else pd.Series([""] * len(df))
                dc = df["DetectionMeasure"].fillna("").astype(str).str.strip() if "DetectionMeasure" in df.columns else pd.Series([""] * len(df))
                m = (dc != "") & (pc == "")
                items = sorted({str(x).strip() for x in df.loc[m, "FailureMode"].tolist() if str(x).strip() and str(x).lower() != "nan"})
                if not items:
                    return _legacy_message("detect_only")
                answer = "只有探测性控制、没有预防性控制的失效模式包括：" + "，".join(items)
                if "合理吗" in q:
                    answer += "。是否合理需要结合工况与成本权衡，但仅从表格信息看，缺少预防控制通常意味着更依赖检测发现问题。"
                return {
                    "answer": answer,
                    "context": ["scope=global", "controls=detect_only", "list=modes", "csv_fallback=true"],
                    "context_raw": items,
                }
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)
                WHERE fd.DetectionMeasure IS NOT NULL AND trim(toString(fd.DetectionMeasure)) <> ''
                  AND (fd.PreventControl IS NULL OR trim(toString(fd.PreventControl)) = '')
                RETURN DISTINCT fd.FailureMode AS FailureMode
                ORDER BY FailureMode
                """.strip(),
                {},
            )
            items = _rows_to_items(rows)
            if not items:
                return None
            answer = "只有探测性控制、没有预防性控制的失效模式包括：" + "，".join(items)
            if "合理吗" in q:
                answer += "。是否合理需要结合工况与成本权衡，但仅从表格信息看，缺少预防控制通常意味着更依赖检测发现问题。"
            return {"answer": answer, "context": ["scope=global", "controls=detect_only", "list=modes"], "context_raw": items}

        return None

    def _try_answer_threats_by_protection_level(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "提高防护等级" not in q:
            return None
        if "外部威胁" not in q:
            return None

        rows_modes = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.PreventControl IS NOT NULL
              AND trim(toString(fd.PreventControl)) <> ''
              AND (toString(fd.PreventControl) CONTAINS '提高防护等级' OR toString(fd.PreventControl) CONTAINS '防护等级')
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY FailureMode
            """.strip(),
            {},
        )
        modes = [str(r.get("FailureMode") or "").strip() for r in rows_modes]
        modes = [m for m in modes if m]
        if not modes:
            # Legacy fallback: infer by FailureMeasure's mixed text
            rows2 = self._query_params(
                """
                MATCH (fd:FailureMode)-[:isDueToFailureCause]->(:FailureCause)-[:isImprovedByFailureMeasure]->(fm:FailureMeasure)
                WHERE fm.FailureMeasure IS NOT NULL
                  AND toString(fm.FailureMeasure) CONTAINS '预防控制：'
                  AND toString(fm.FailureMeasure) CONTAINS '提高防护等级'
                RETURN DISTINCT fd.FailureMode AS FailureMode
                ORDER BY FailureMode
                """.strip(),
                {},
            )
            modes = [str(r.get("FailureMode") or "").strip() for r in rows2]
            modes = [m for m in modes if m]
            if not modes:
                return None

        threats: list[str] = []
        blob = " ".join(modes)
        if "灰尘" in blob or "粉尘" in blob or "进灰" in blob or "尘" in blob:
            threats.append("灰尘/粉尘")
        if "进水" in blob or "水" in blob:
            threats.append("进水/水侵")
        if "潮" in blob or "湿" in blob:
            threats.append("潮湿/凝露")

        if not threats:
            # Fallback: use the most indicative failure-mode wordings.
            threats = modes[:4]

        answer = "提高防护等级（如 IP 等级）主要用于抵御外部威胁：" + "，".join(threats) + "。"
        return {
            "answer": answer,
            "context": ["scope=global", "prevent_kw=提高防护等级", "list=threats"],
            "context_raw": {"threats": threats, "modes": modes},
        }

    def _try_answer_failure_causes_by_prevent_control(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "预防措施" not in q:
            return None
        if "失效原因" not in q:
            return None

        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:isDueToFailureCause]->(fc:FailureCause)
            WHERE fd.PreventControl IS NOT NULL
              AND trim(toString(fd.PreventControl)) <> ''
              AND toString(fd.PreventControl) CONTAINS $kw
            RETURN DISTINCT fc.FailureCause AS FailureCause
            ORDER BY FailureCause
            """.strip(),
            {"kw": kw},
        )
        items = [str(r.get("FailureCause") or "").strip() for r in rows]
        items = [x for x in items if x]
        if not items:
            # Legacy fallback: Prevent control may only exist inside FailureMeasure text.
            rows2 = self._query_params(
                """
                MATCH (fd:FailureMode)-[:isDueToFailureCause]->(fc:FailureCause)-[:isImprovedByFailureMeasure]->(fm:FailureMeasure)
                WHERE fm.FailureMeasure IS NOT NULL
                  AND toString(fm.FailureMeasure) CONTAINS '预防控制：'
                  AND toString(fm.FailureMeasure) CONTAINS $kw
                RETURN DISTINCT fc.FailureCause AS FailureCause
                ORDER BY FailureCause
                """.strip(),
                {"kw": kw},
            )
            items = [str(r.get("FailureCause") or "").strip() for r in rows2]
            items = [x for x in items if x]
            if not items:
                return None

        if len(items) == 1:
            answer = f"“{kw}”这一预防措施主要是为了防止的失效原因是：{items[0]}。"
        else:
            answer = f"“{kw}”这一预防措施主要关联/防止的失效原因包括：" + "，".join(items) + "。"

        return {
            "answer": answer,
            "context": ["scope=global", f"prevent_kw={kw}", "list=causes"],
            "context_raw": items,
        }

    def _try_answer_modes_by_cause_keyword(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "原因" not in q or "失效模式" not in q:
            return None
        if not ("出现在哪些" in q or "出现在哪些不同" in q):
            return None
        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:isDueToFailureCause]->(fc:FailureCause)
            WHERE fc.FailureCause CONTAINS $kw
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY FailureMode
            """.strip(),
            {"kw": kw},
        )
        items = [str(r.get("FailureMode") or "").strip() for r in rows]
        items = [x for x in items if x]
        if not items:
            return None
        answer = f"原因包含“{kw}”的失效模式包括：" + "，".join(items)
        return {
            "answer": answer,
            "context": ["scope=global", f"cause_kw={kw}", "list=modes"],
            "context_raw": items,
        }

    def _try_answer_modes_by_cause_phrase_quoted(self, question: str) -> dict | None:
        """Deterministic answer for: given a quoted cause phrase, return related failure mode(s).

        Targets questions like:
        - “X”会导致什么后果？
        - “X”具体指哪个失效模式？
        - “X”被列为哪些失效模式的原因？

        This is intentionally strict to avoid hijacking analytical questions.
        """

        q = (question or "").strip()
        if not q:
            return None

        # Must contain a quoted phrase.
        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        cause = str(kws[0]).strip()
        if not cause:
            return None

        # Candidate causes to try (start with the user phrase itself).
        cause_candidates = [cause]

        # Only handle the specific 'cause -> mode' intents.
        intent_markers = (
            "会导致什么后果",
            "导致什么后果",
            "指哪个失效模式",
            "具体指哪个失效模式",
            "对应的失效",
            "被列为哪些失效模式的原因",
            "哪些失效模式的原因",
        )
        if not any(m in q for m in intent_markers):
            return None

        def _lookup_modes_by_causes(tries: list[str]) -> tuple[list[str], str | None]:
            # 1) Prefer exact match (prevents over-broad CONTAINS matches).
            for c in tries:
                rows = self._query_params(
                    """
                    MATCH (fd:FailureMode)-[:isDueToFailureCause]->(fc:FailureCause)
                    WHERE fc.FailureCause = $cause
                    RETURN DISTINCT fd.FailureMode AS FailureMode
                    ORDER BY FailureMode
                    """.strip(),
                    {"cause": c},
                )
                items = [str(r.get("FailureMode") or "").strip() for r in rows]
                items = [x for x in items if x]
                if items:
                    return items, c

            # 2) Fallback to substring match.
            for c in tries:
                rows = self._query_params(
                    """
                    MATCH (fd:FailureMode)-[:isDueToFailureCause]->(fc:FailureCause)
                    WHERE fc.FailureCause CONTAINS $cause
                    RETURN DISTINCT fd.FailureMode AS FailureMode
                    ORDER BY FailureMode
                    """.strip(),
                    {"cause": c},
                )
                items = [str(r.get("FailureMode") or "").strip() for r in rows]
                items = [x for x in items if x]
                if items:
                    return items, c

            return [], None

        items, resolved_cause = _lookup_modes_by_causes(cause_candidates)

        # If still not found, do a deterministic "smart mapping" from a generic user phrase
        # to the closest existing FailureCause in the current graph.
        if not items:
            def _norm_text(s: str) -> str:
                s = (s or "").strip()
                s = re.sub(r"[\s,，。\.；;:：、/\\]+", "", s)
                for w in [
                    "不合理",
                    "异常",
                    "不良",
                    "损坏",
                    "失效",
                    "故障",
                    "问题",
                    "不足",
                    "不工作",
                    "未工作",
                    "不受控制",
                    "不受控",
                ]:
                    s = s.replace(w, "")
                # Often described in graph as BMS/SOC 算法，而用户会说“软件算法”
                s = s.replace("软件", "")
                return s

            def _bigrams(s: str) -> set[str]:
                if not s:
                    return set()
                if len(s) == 1:
                    return {s}
                return {s[i : i + 2] for i in range(len(s) - 1)}

            def _jaccard(a: set[str], b: set[str]) -> float:
                if not a or not b:
                    return 0.0
                inter = len(a & b)
                union = len(a | b)
                return inter / union if union else 0.0

            def _focus_keywords(user_phrase: str) -> list[str]:
                t = user_phrase or ""
                kws: list[str] = []
                if ("算法" in t) or ("软件" in t) or ("程序" in t):
                    kws += ["算法", "SOC", "BMS", "软件", "程序"]
                if ("元器件" in t) or ("器件" in t):
                    kws += ["元器件", "器件"]
                if "风扇" in t:
                    kws += ["风扇"]
                seen = set()
                out: list[str] = []
                for k in kws:
                    if k not in seen:
                        seen.add(k)
                        out.append(k)
                return out

            focus = _focus_keywords(cause)
            if focus:
                rows = self._query_params(
                    """
                    MATCH (fc:FailureCause)
                    RETURN DISTINCT fc.FailureCause AS cause
                    """.strip(),
                    {},
                )
                all_causes = [str(r.get("cause") or "").strip() for r in rows]
                all_causes = [c for c in all_causes if c]

                # Filter by focus keywords first to reduce false positives.
                filtered = [c for c in all_causes if any(k in c for k in focus)]
                if not filtered:
                    filtered = all_causes

                u = _norm_text(cause)
                u_bg = _bigrams(u)
                scored: list[tuple[float, str]] = []
                for c in filtered:
                    c_norm = _norm_text(c)
                    s = _jaccard(u_bg, _bigrams(c_norm))
                    if any(k in c for k in focus):
                        s += 0.05
                    scored.append((s, c))
                scored.sort(key=lambda x: x[0], reverse=True)

                # Conservative threshold to avoid wrong auto-maps.
                mapped = [c for s, c in scored if s >= 0.15][:5]
                if mapped:
                    items, resolved_cause = _lookup_modes_by_causes(mapped)

        if not items:
            return None

        if len(items) == 1:
            answer = f"{items[0]}。"
        else:
            answer = "对应的失效模式包括：" + "，".join(items)

        ctx = ["scope=global", f"cause_phrase={cause}", "mode_lookup=by_cause"]
        if resolved_cause and resolved_cause != cause:
            ctx.append(f"cause_resolved={resolved_cause}")
        return {"answer": answer, "context": ctx, "context_raw": items}

    def _try_answer_prevent_control_types(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "现行预防性" not in q or "设计控制" not in q:
            return None
        if not ("有哪些类型" in q or "主要有哪些类型" in q):
            return None

        # Prefer dedicated property on FailureMode (newer graphs)
        rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.PreventControl IS NOT NULL AND trim(toString(fd.PreventControl)) <> ''
            RETURN DISTINCT toString(fd.PreventControl) AS v
            """.strip(),
            {},
        )
        items = [str(r.get("v") or "").strip() for r in rows]
        items = [x for x in items if x and x.lower() != "nan"]

        # Fallback: parse combined FailureMeasure text (older graphs)
        if not items:
            rows = self._query_params(
                """
                MATCH (fm:FailureMeasure)
                WHERE fm.FailureMeasure IS NOT NULL AND toString(fm.FailureMeasure) CONTAINS '预防控制：'
                RETURN DISTINCT toString(fm.FailureMeasure) AS v
                """.strip(),
                {},
            )
            blob = [str(r.get("v") or "").strip() for r in rows]
            blob = [b for b in blob if b]
            extracted: list[str] = []
            for b in blob:
                m = re.search(r"预防控制：([^；]+)", b)
                if m:
                    extracted.append(m.group(1).strip())
            items = [x for x in extracted if x]

        if not items:
            return None

        # Categorize with examples
        cats: list[tuple[str, list[str]]] = []

        def _pick_examples(pred, limit=3):
            ex = [x for x in items if pred(x)]
            # stable order
            seen = set()
            out = []
            for x in ex:
                if x not in seen:
                    seen.add(x)
                    out.append(x)
                if len(out) >= limit:
                    break
            return out

        examples_protect = _pick_examples(lambda x: "防护" in x or "IP" in x)
        if examples_protect:
            cats.append(("提高防护等级/防护设计", examples_protect))

        examples_std = _pick_examples(lambda x: "标准" in x)
        if examples_std:
            cats.append(("设定标准/阈值", examples_std))

        examples_upgrade = _pick_examples(lambda x: "升级" in x or "算法" in x or "SOC" in x or "BMS" in x)
        if examples_upgrade:
            cats.append(("系统/软件升级与算法优化", examples_upgrade))

        examples_mark = _pick_examples(lambda x: "颜色" in x or "材料" in x or "区分" in x)
        if examples_mark:
            cats.append(("标识与材料区分", examples_mark))

        # Other bucket
        used = set(sum((ex for _, ex in cats), []))
        others = [x for x in items if x not in used]
        if others:
            cats.append(("其他", others[:3]))

        parts = []
        for name, ex in cats:
            if ex:
                parts.append(f"{name}（例如：" + "、".join(ex) + "）")
            else:
                parts.append(name)

        answer = "文档中提到的现行预防性设计控制主要类型包括：" + "；".join(parts) + "。"
        return {
            "answer": answer,
            "context": ["scope=global", "control=prevent", "type_summary"],
            "context_raw": {"items": items, "categories": cats},
        }

    def _try_answer_detect_control_types(self, question: str) -> dict | None:
        q = (question or "").strip()
        if not q:
            return None
        if "现行探测性" not in q or "设计控制" not in q:
            return None
        if not ("有哪些类型" in q or "主要有哪些类型" in q):
            return None

        # Prefer dedicated property on FailureMode (newer graphs)
        rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.DetectionMeasure IS NOT NULL AND trim(toString(fd.DetectionMeasure)) <> ''
            RETURN DISTINCT toString(fd.DetectionMeasure) AS v
            """.strip(),
            {},
        )
        items = [str(r.get("v") or "").strip() for r in rows]
        items = [x for x in items if x and x.lower() != "nan"]

        # Fallback: use FailureMeasure node's DetectionMeasure property
        if not items:
            rows = self._query_params(
                """
                MATCH (fm:FailureMeasure)
                WHERE fm.DetectionMeasure IS NOT NULL AND trim(toString(fm.DetectionMeasure)) <> ''
                RETURN DISTINCT toString(fm.DetectionMeasure) AS v
                """.strip(),
                {},
            )
            items = [str(r.get("v") or "").strip() for r in rows]
            items = [x for x in items if x and x.lower() != "nan"]

        if not items:
            return None

        def _uniq_keep_order(xs: list[str]) -> list[str]:
            seen = set()
            out = []
            for x in xs:
                if x not in seen:
                    seen.add(x)
                    out.append(x)
            return out

        items = _uniq_keep_order(items)

        # Group into types the question expects: 测试/检查/测量/试验/检测/保护
        def _ex(pred, limit=4):
            return [x for x in items if pred(x)][:limit]

        groups: list[tuple[str, list[str]]] = []

        ex_test = _ex(lambda x: "测试" in x)
        if ex_test:
            groups.append(("测试", ex_test))

        ex_detect = _ex(lambda x: "检测" in x or "绝缘" in x or "漏电" in x)
        if ex_detect:
            groups.append(("检测", ex_detect))

        ex_measure = _ex(lambda x: "测量" in x or "万用表" in x)
        if ex_measure:
            groups.append(("测量", ex_measure))

        ex_trial = _ex(lambda x: "试验" in x or "挤压" in x or "震动" in x or "老化" in x or "阻燃" in x)
        if ex_trial:
            groups.append(("试验/验证", ex_trial))

        ex_check = _ex(lambda x: "检查" in x or "目视" in x)
        if ex_check:
            groups.append(("检查", ex_check))

        ex_protect = _ex(lambda x: "保护" in x or "报警" in x)
        if ex_protect:
            groups.append(("保护/监测", ex_protect))

        used = set(sum((ex for _, ex in groups), []))
        others = [x for x in items if x not in used]
        if others:
            groups.append(("其他", others[:4]))

        parts = []
        for name, ex in groups:
            if ex:
                parts.append(f"{name}（例如：" + "、".join(ex) + "）")
            else:
                parts.append(name)
        answer = "文档中提到的现行探测性设计控制主要类型包括：" + "；".join(parts) + "。"
        return {
            "answer": answer,
            "context": ["scope=global", "control=detect", "type_summary"],
            "context_raw": {"items": items, "groups": groups},
        }

    def _try_answer_projects_by_detection_measure(self, question: str) -> dict | None:
        """Deterministic answer for: '“X”主要应用于哪些设计项目？' where X is a detective control.

        Why: This is a pure table-lookup question. LLM often over-generalizes and returns unrelated projects.
        """

        q = (question or "").strip()
        if not q:
            return None
        if "主要应用于" not in q:
            return None
        if "设计项目" not in q and "项目" not in q:
            return None
        kws = re.findall(r"“([^”]+)”", q)
        if not kws:
            return None
        kw = str(kws[0]).strip()
        if not kw:
            return None

        rows = self._query_params(
            """
            MATCH (ps:ProcessStep)<-[:occursAtProcessStep]-(fd:FailureMode)
            WHERE (
                fd.DetectionMeasure IS NOT NULL AND trim(toString(fd.DetectionMeasure)) <> ''
                AND toString(fd.DetectionMeasure) CONTAINS $kw
            ) OR EXISTS {
                MATCH (fd)-[:isDueToFailureCause]->(:FailureCause)-[:isImprovedByFailureMeasure]->(fm:FailureMeasure)
                WHERE fm.DetectionMeasure IS NOT NULL AND trim(toString(fm.DetectionMeasure)) <> ''
                  AND toString(fm.DetectionMeasure) CONTAINS $kw
            }
            RETURN DISTINCT ps.ProcessStep AS ProcessStep
            ORDER BY ProcessStep
            """.strip(),
            {"kw": kw},
        )
        items = [str(r.get("ProcessStep") or "").strip() for r in rows]
        items = [x for x in items if x]
        if not items:
            return None

        if len(items) == 1:
            answer = f"{kw} 主要应用于：{items[0]}。"
        else:
            answer = f"{kw} 主要应用于以下设计项目：" + "，".join(items) + "。"

        return {
            "answer": answer,
            "context": ["scope=global", f"detect_kw={kw}", "list=projects"],
            "context_raw": items,
        }

    @staticmethod
    def _extract_metric_any(question: str) -> str | None:
        q = (question or "")
        if "严重度" in q or re.search(r"\bS\b", q, re.IGNORECASE):
            return "S"
        if "频度" in q or "发生度" in q or re.search(r"\bO\b", q, re.IGNORECASE):
            return "O"
        if "探测度" in q or "检测度" in q or re.search(r"\bD\b", q, re.IGNORECASE):
            return "D"
        if "RPN" in q.upper():
            return "RPN"
        return None

    def _try_answer_per_mode_metric_by_process_step(self, question: str) -> dict | None:
        """Deterministic answer for: 'X 对应的每个失效模式的 RPN/S/O/D 分别是多少'."""
        q = (question or "").strip()
        if not q:
            return None
        if "失效模式" not in q:
            return None
        if not ("分别" in q or "分别是" in q or "各" in q or "每个" in q):
            return None

        metric = self._extract_metric_any(q)
        if not metric:
            return None

        ps_key = self._extract_process_step_general(q)
        if not ps_key:
            return None
        matched_name = self._match_process_step_name(ps_key)
        if not matched_name:
            return None

        rows = self._query_params(
            f"""
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {{ProcessStep: $step}})
            WITH fd
            WHERE fd.{metric} IS NOT NULL
            RETURN fd.FailureMode AS FailureMode, toFloat(fd.{metric}) AS val
            ORDER BY fd.FailureMode
            """.strip(),
            {"step": matched_name},
        )
        items: list[dict[str, object]] = []
        for r in rows:
            fm = str(r.get("FailureMode") or "").strip()
            v = r.get("val")
            if not fm or v is None:
                continue
            try:
                vv = float(v)
            except Exception:
                continue
            items.append({"FailureMode": fm, metric: vv})

        if not items:
            return None

        metric_name = {"S": "严重度", "O": "频度数", "D": "探测度数", "RPN": "RPN"}.get(metric, metric)
        answer = f"{matched_name} 对应的每个失效模式的{metric_name}如下：" + "；".join(
            f"{it['FailureMode']}={int(it[metric]) if float(it[metric]).is_integer() else it[metric]}" for it in items
        )
        return {
            "answer": answer,
            "context": [f"ProcessStep={matched_name}", f"metric={metric}", "per_mode=1"],
            "context_raw": items,
        }

    def _try_answer_extreme_metric_mode_by_process_step(self, question: str) -> dict | None:
        """Deterministic answer for extreme metric questions.

        Examples:
        - X 对应的 RPN 最大/最小 的失效模式是哪些
        - X 对应的失效模式里，哪个探测度最高
        """
        q = (question or "").strip()
        if not q:
            return None
        if "失效模式" not in q:
            return None
        metric = self._extract_metric_any(q)
        if not metric:
            return None

        want_max = any(k in q for k in ("最大", "最高"))
        want_min = any(k in q for k in ("最小", "最低"))
        if not (want_max or want_min):
            return None

        ps_key = self._extract_process_step_general(q)
        if not ps_key:
            return None
        matched_name = self._match_process_step_name(ps_key)
        if not matched_name:
            return None

        agg_fn = "max" if want_max else "min"
        rows = self._query_params(
            f"""
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {{ProcessStep: $step}})
            WHERE fd.{metric} IS NOT NULL
            RETURN {agg_fn}(toFloat(fd.{metric})) AS extreme
            """.strip(),
            {"step": matched_name},
        )
        extreme = rows[0].get("extreme") if rows else None
        if extreme is None:
            return None
        try:
            extreme_val = float(extreme)
        except Exception:
            return None

        modes = self._query_params(
            f"""
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {{ProcessStep: $step}})
            WHERE fd.{metric} IS NOT NULL AND toFloat(fd.{metric}) = $v
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY fd.FailureMode
            """.strip(),
            {"step": matched_name, "v": extreme_val},
        )
        items = [str(r.get("FailureMode") or "").strip() for r in modes]
        items = [x for x in items if x]
        if not items:
            return None

        metric_name = {"S": "严重度", "O": "频度数", "D": "探测度数", "RPN": "RPN"}.get(metric, metric)
        word = "最大" if want_max else "最小"
        extreme_text = str(int(extreme_val)) if float(extreme_val).is_integer() else str(extreme_val)
        answer = f"{matched_name} 对应的{metric_name}{word}值为 {extreme_text}，对应失效模式：" + "，".join(items)
        return {
            "answer": answer,
            "context": [f"ProcessStep={matched_name}", f"metric={metric}", f"extreme={'max' if want_max else 'min'}"],
            "context_raw": {"value": extreme_val, "modes": items},
        }

    def _try_answer_modes_effects_causes_by_process_step(self, question: str) -> dict | None:
        """Deterministic answer for: 'X 对应的失效模式、后果、原因分别是什么（列出来）'."""
        q = (question or "").strip()
        if not q:
            return None
        if not ("失效模式" in q and ("后果" in q or "失效后果" in q) and ("原因" in q or "失效原因" in q)):
            return None

        ps_key = self._extract_process_step_general(q)
        if not ps_key:
            return None
        matched_name = self._match_process_step_name(ps_key)
        if not matched_name:
            return None

        rows = self._query_params(
            """
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep {ProcessStep: $step})
            OPTIONAL MATCH (fd)-[:resultsInFailureEffect]->(fe:FailureEffect)
            OPTIONAL MATCH (fd)-[:isDueToFailureCause]->(fc:FailureCause)
            RETURN fd.FailureMode AS FailureMode,
                   collect(DISTINCT fe.FailureEffect) AS Effects,
                   collect(DISTINCT fc.FailureCause) AS Causes
            ORDER BY fd.FailureMode
            """.strip(),
            {"step": matched_name},
        )
        items: list[dict[str, object]] = []
        for r in rows:
            fm = str(r.get("FailureMode") or "").strip()
            if not fm:
                continue
            eff = [str(x).strip() for x in (r.get("Effects") or []) if str(x).strip()]
            cau = [str(x).strip() for x in (r.get("Causes") or []) if str(x).strip()]
            items.append({"FailureMode": fm, "FailureEffect": eff, "FailureCause": cau})

        if not items:
            return None

        # 只生成简洁文本；详细数据放 context_raw
        parts = []
        for it in items:
            eff = " / ".join(it["FailureEffect"]) if it["FailureEffect"] else ""
            cau = " / ".join(it["FailureCause"]) if it["FailureCause"] else ""
            parts.append(f"{it['FailureMode']}（后果：{eff or '无'}；原因：{cau or '无'}）")
        answer = f"{matched_name} 对应的失效模式/后果/原因如下：" + "；".join(parts)
        return {
            "answer": answer,
            "context": [f"ProcessStep={matched_name}", "modes_effects_causes=1"],
            "context_raw": items,
        }

    # 参数：question(str)；返回：dict（包含 answer/answer_file/context/context_raw）；功能：完整问答流程：先让模型生成 Cypher 并查图，查不到再走向量检索，最后让模型基于上下文生成中文答案。
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

        # === Global / cross-project deterministic branches (avoid LLM for objective table-lookup questions) ===
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
            try:
                self._ensure_vector_index()
                results = self.similarity_search(question, k=self.top_k)
                query_result = [result.page_content for result in results]
            except Exception as e:
                msg = str(e)
                if "no such vector schema index" in msg.lower() or "vector schema index" in msg.lower():
                    raise RuntimeError(
                        "向量索引不存在或不可用（默认名：vector）。"
                        "这通常发生在：建图未完整执行到向量索引阶段、连接到了不同的 NEO4J_DATABASE、"
                        "或索引被手工删除。请重新调用 /api/v1/create-fmea-graph，"
                        "并确认 .env 的 NEO4J_DATABASE 与建图时一致；"
                        "也可通过环境变量 NEO4J_VECTOR_INDEX_NAME 指定索引名。"
                    ) from e
                raise

        # Summarize the query results for further processing
        for result in query_result:
            result_summarize = self.run_inference(
                [self.summarize_context(context=json.dumps(result), question=question)]
            )
            pre_answer.append(result_summarize.choices[0].message.content)

        # Add question and context to QA context
        self.qa_prompt_context(question, json.dumps(pre_answer, ensure_ascii=False))

        # Run inference
        qa_temp_raw = (getenv("OPENAI_QA_TEMPERATURE", "0") or "0").strip()
        try:
            qa_temp = float(qa_temp_raw)
        except Exception:
            qa_temp = 0.0
        answer = self.run_inference(list(self.context_qa), temperature=qa_temp)

        answer_text = answer.choices[0].message.content
        answer_file = self._save_answer_to_file(answer_text)

        return {
            "answer": answer_text,
            "answer_file": answer_file,
            "context": pre_answer,
            "context_raw": query_result,
        }

# ------------------------------------------------------------------------------------------------------------------

# RAG SERVICE (lazy init)
#
# Why: `Neo4jVector.__init__` 会立即 `verify_connectivity()`。
# 当 NEO4J_URL 指向 Aura 但当前机器无法解析外网域名/无网络时，
# 若在模块加载阶段就初始化，会导致 `python code/kg_rag.py` 直接崩溃、服务无法启动。
_rag_service = None
_rag_service_init_error: Exception | None = None
_rag_service_lock = threading.Lock()


def _neo4j_url_host_port(url: str | None) -> tuple[str | None, int | None]:
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

# API ENDPOINTS
def create_graph(body: object):
    try:
        path = body.get("path") if isinstance(body, dict) else None
        if not path:
            return _json_response(_as_problem("Bad Request", "缺少字段: path", 400), 400)
        rag = get_rag_service()
        ok = rag.create_fmea_graph(csv_file=path)
        if not ok:
            return _json_response(
                _as_problem("Internal Server Error", "建图失败：请检查 CSV 路径、Neo4j 连接与写入权限。", 500), 500
            )
        return _json_response(True, 200)
    except RuntimeError as e:
        # 通常是 Neo4j 初始化失败（DNS/网络/账号）
        return _json_response(_as_problem("Service Unavailable", str(e), 503), 503)
    except Exception as e:
        return _json_response(_as_problem("Internal Server Error", f"建图异常：{e}", 500), 500)


def answer_question(body: object):
    try:
        question = body.get("question") if isinstance(body, dict) else None
        if question is None:
            return _json_response(_as_problem("Bad Request", "缺少字段: question", 400), 400)
        rag = get_rag_service()
        return _json_response(rag.answer_question(str(question)), 200)
    except ValueError as e:
        return _json_response(_as_problem("Bad Request", str(e), 400), 400)
    except RuntimeError as e:
        msg = str(e)
        # 业务前置条件未满足：未建图/未初始化
        if "知识图谱尚未初始化" in msg:
            return _json_response(_as_problem("Conflict", msg, 409), 409)
        # Neo4j 初始化失败
        if "Neo4j 连接初始化失败" in msg:
            return _json_response(_as_problem("Service Unavailable", msg, 503), 503)
        return _json_response(_as_problem("Internal Server Error", f"问答异常：{msg}", 500), 500)
    except Exception as e:
        return _json_response(_as_problem("Internal Server Error", f"问答异常：{e}", 500), 500)


def set_top_k(body: object):
    try:
        top_k = body.get("top_k") if isinstance(body, dict) else None
        if top_k is None:
            return _json_response(_as_problem("Bad Request", "缺少字段: top_k", 400), 400)
        rag = get_rag_service()
        return _json_response(rag.set_top_k(int(top_k)), 200)
    except RuntimeError as e:
        return _json_response(_as_problem("Service Unavailable", str(e), 503), 503)
    except Exception as e:
        return _json_response(_as_problem("Bad Request", f"top_k 非法：{e}", 400), 400)


def clear_graph(body: object):
    try:
        confirm = body.get("confirm") if isinstance(body, dict) else None
        if confirm is not True:
            return _json_response(
                _as_problem("Bad Request", "缺少字段: confirm（必须为 true）", 400),
                400,
            )
        rag = get_rag_service()
        return _json_response(rag.clear_fmea_graph(), 200)
    except RuntimeError as e:
        return _json_response(_as_problem("Service Unavailable", str(e), 503), 503)
    except Exception as e:
        return _json_response(_as_problem("Internal Server Error", f"清空异常：{e}", 500), 500)


# MAIN ENTRYPOINT
if __name__ == "__main__":
    app = connexion.FlaskApp(__name__)
    app.add_api("api.yml")
    application = app.app
    # 让中文以 unicode 形式输出（\uXXXX），避免终端/客户端编码不一致。
    # 可通过环境变量 JSON_UNICODE_ESCAPE 控制：1/true=开启（默认），0/false=关闭。
    json_unicode_escape = (getenv("JSON_UNICODE_ESCAPE", "1") or "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    try:
        # Flask 2.2+/3.x
        if hasattr(application, "json") and application.json is not None:
            application.json.ensure_ascii = json_unicode_escape
        else:
            # Older Flask
            application.config["JSON_AS_ASCII"] = json_unicode_escape
    except Exception:
        pass
    app.run(port=8080)