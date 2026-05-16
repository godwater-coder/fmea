# -*- coding: utf-8 -*-

# 该文件提供服务运维与通用能力，包括 CSV 读取、索引维护、图操作与 LLM 调用工具方法。

from os import getenv
from datetime import datetime
import time
import re
import collections
import openai
import json
import os
from pathlib import Path
import pandas as pd
import graph_building

from synonyms import CSV_COLUMN_SYNONYMS, PROCESS_STEP_SUFFIX_PATTERN

from ..settings import (
    OLLAMA_API_KEY,
    NEO4J_URL,
    NEO4J_USERNAME,
    NEO4J_PASSWORD,
    NEO4J_DATABASE,
    CYPHER_GENERATION_TEMPLATE,
    CYPHER_QUESTION_TEMPLATE,
    CYPHER_QA_TEMPLATE,
    ANSWER_SUMMARIZE_TEMPLATE,
)


class ServiceOpsMixin:
    @staticmethod
    def _default_dfmea_csv_path() -> str | None:
        try:
            # 向上回溯到项目根目录，兼容 service 子目录拆分后的路径层级。
            p = Path(__file__).resolve().parents[3] / "data" / "dfmea_final.csv"
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

        rename: dict[str, str] = {}
        existing_cols = set(df.columns)
        for original in list(df.columns):
            target = CSV_COLUMN_SYNONYMS.get(_norm_col(original))
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

    @staticmethod
    def _dedupe_keep_order(items: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for x in items:
            s = str(x or "").strip()
            if not s or s in seen:
                continue
            seen.add(s)
            out.append(s)
        return out

    def _preprocess_question_for_retrieval(self, question: str) -> dict[str, object]:
        """Normalize and rewrite question for vector retrieval before QA routing."""
        q = str(question or "").strip()
        q_norm = re.sub(r"\s+", " ", q).strip()
        variants: list[str] = [q_norm]

        metric = self._extract_metric_any(q_norm)
        slot = self._extract_extreme_followup_slot(q_norm)
        slot_map = {
            "temp": "临时措施",
            "prevent": "预防性设计控制",
            "detect": "探测性设计控制",
            "design_controls": "现行设计控制措施",
            "cause": "失效原因",
            "effect": "失效后果",
        }

        # 对“复合约束问题”做显式改写，避免只命中前半句语义。
        if metric and slot and "失效模式" in q_norm:
            slot_name = slot_map.get(slot, "目标字段")
            variants.append(
                f"{q_norm}。请先确定{metric}极值对应的失效模式，再返回该失效模式的{slot_name}。"
            )

        # 对排除语义做显式改写，提升向量检索召回准确度。
        ex_terms = self._extract_exclusion_terms(q_norm)
        if ex_terms:
            variants.append(f"{q_norm}。注意排除：{'，'.join(ex_terms)}。")

        variants = self._dedupe_keep_order(variants)
        if len(variants) > self.query_rewrite_count:
            variants = variants[: self.query_rewrite_count]

        return {
            "original": q,
            "normalized": q_norm,
            "rag_query": variants[0] if variants else q_norm,
            "query_variants": variants,
            "metric": metric,
            "slot": slot,
            "exclusion_terms": ex_terms,
        }

    def _vector_search_multi_queries(self, queries: list[str], k: int) -> list[str]:
        hits: list[str] = []
        seen: set[str] = set()
        each_k = max(k, min(8, k * 2))

        for q in queries:
            results = self.similarity_search(q, k=each_k)
            for result in results:
                text = str(getattr(result, "page_content", "") or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                hits.append(text)
            if len(hits) >= each_k:
                break

        return hits[:each_k]

    def _answer_question_via_vector_rag(self, prep: dict[str, object]) -> dict:
        """Vector-first QA path using preprocessed/re-written queries."""
        question_original = str(prep.get("original") or "").strip()
        question_for_retrieval = str(prep.get("rag_query") or question_original)
        query_variants = [str(x) for x in (prep.get("query_variants") or []) if str(x).strip()]
        if not query_variants:
            query_variants = [question_for_retrieval]

        pre_answer: list[str] = []

        # 先尝试图查询（让 LLM 生成 Cypher），使用预处理后的检索问题。
        self.cypher_prompt_context(question_for_retrieval)
        result = self.run_inference(self.context_cypher)
        cypher_query = self.extract_cypher(result.choices[0].message.content)

        if self.validate_cypher(cypher_query):
            query_result = self.query(cypher_query)
            if len(query_result) > self.top_k:
                query_result = query_result[: self.top_k]
        else:
            query_result = None

        if not query_result:
            # 图查询失败时，走“多改写问题”的向量检索。
            try:
                self._ensure_vector_index()
                query_result = self._vector_search_multi_queries(query_variants, k=self.top_k)
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

        # 对检索结果做摘要压缩，再用于最终回答。
        for r in query_result:
            result_summarize = self.run_inference(
                [self.summarize_context(context=json.dumps(r, ensure_ascii=False), question=question_original)]
            )
            pre_answer.append(result_summarize.choices[0].message.content)

        self.qa_prompt_context(question_original, json.dumps(pre_answer, ensure_ascii=False))
        qa_temp_raw = (getenv("OLLAMA_QA_TEMPERATURE", "0") or "0").strip()
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

    # 最关键的“直接调用大模型 API”的函数：它把 messages=context 发给 Ollama 的 OpenAI 兼容接口，
    # 默认指向本地 Ollama，再把模型返回的补全结果对象原样返回。
    # 参数：context(list[dict])、temperature(float)、max_tokens(int)；返回：聊天补全结果对象；功能：调用 LLM 接口让模型基于上下文生成内容。
    def run_inference(
        self, context: list[dict], temperature: float = 0.0, max_tokens: int = 4000
    ):
        """
        调用 Ollama 兼容接口进行推理。

        Args:
            context (list): 消息上下文列表（每项为 dict，包含 role/content 等字段）。
            temperature (float): 生成随机性，越大越发散。
            max_tokens (int): 最大生成 token 数。

        Returns:
            object: 聊天补全结果对象（可通过 choices[0].message.content 取文本）。
        """
        model = getenv("OLLAMA_MODEL", "qwen3.6:27b")
        api_base = (
            getenv("OLLAMA_API_BASE")
            or getenv("OLLAMA_BASE_URL")
            or "http://127.0.0.1:11434/v1"
        )

        # 优先使用：OpenAI Python SDK v1+，通过兼容接口访问本地 Ollama。
        # 返回的是响应对象，仍可通过 `.choices[0].message.content` 读取生成文本。
        if hasattr(openai, "OpenAI"):
            client_kwargs = {}
            if OLLAMA_API_KEY:
                client_kwargs["api_key"] = OLLAMA_API_KEY
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
        engine = getenv("OLLAMA_ENGINE")
        legacy_kwargs = {
            "messages": context,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if engine:
            return openai.ChatCompletion.create(engine=engine, **legacy_kwargs)
        return openai.ChatCompletion.create(model=model, **legacy_kwargs)

    # 把“图里的一个 FailureMode（失效模式）周围相关联的信息”取出来，拼成一段可被向量化的文本，用来建立向量索引（RAG 的检索库）。
    # 参数：failureEffectId(str)；返回：list[dict]；功能：委托 graph_building 中的遍历查询实现。
    def traverse_graph(self, failureEffectId: str) -> list[dict]:
        """
        Returns a list of nodes and relations for a given failure measure id.

        Args:
            failureMeasureId (str): The failure measure id to traverse the graph for.

        Returns:
            list[dict]: A list of nodes and relations.
        """
        return graph_building.traverse_graph(self, failureEffectId)

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
        return graph_building.get_failure_mode_ids(self)

    # 参数：无（仅用 self 查询）；返回：list[dict]；功能：查询所有 FailureMeasure 节点的 Neo4j 内部 ID 列表。
    def get_failure_measure_ids(self) -> list[dict]:
        """
        Get all failure measure ids.

        Returns:
            list[dict]: A list of failure measure ids.
        """
        return graph_building.get_failure_measure_ids(self)

    # 一个用从CSV文件创建FMEA节点的方法
    def create_fmea_graph(self, csv_file: str) -> bool:
        """
        Create the FMEA graph.

        Args:
            csv_file (str): The path to the csv file containing the FMEA data.

        Returns:
            bool: True if the graph was created successfully, False otherwise.

        """
        return graph_building.create_fmea_graph(self, csv_file)

    # 在已经把 FMEA 的节点/关系写进 Neo4j 之后，再把每个失效模式相关的一坨信息“打包成文本 → 向量化 → 存到 Neo4j 的向量索引里
    def create_vector_embeddings(self) -> bool:
        """
        Create vector embeddings for the FMEA graph.

        Returns:
            bool: True if the vector embeddings were created successfully, False otherwise.
        """
        return graph_building.create_vector_embeddings(self)

    # 参数：nodes(list[dict])；返回：(chunk(str), nodeIds(dict))；功能：把遍历到的节点记录去重汇总后拼成一段可检索文本，并同时收集相关节点 ID 作为元数据。
    def create_chunk(self, nodes: list[dict]) -> tuple[str, dict]:
        """
        Create a chunk from a list of nodes.

        Args:
            nodes (list[dict]): A list of nodes.

        Returns:
            tuple[str, dict]: chunk 文本及关联节点元数据。
        """
        return graph_building.create_chunk(nodes)

    @staticmethod
    def _normalize_process_step_name(name: str) -> str:
        s = (name or "").strip()
        # 常见问法会把“设计项目/项目/工序/过程步骤”等后缀带进实体里；图里通常只存核心名称。
        s = re.sub(PROCESS_STEP_SUFFIX_PATTERN, "", s).strip()
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

    @staticmethod
    def _extract_exclusion_terms(question: str) -> list[str]:
        """Extract exclusion phrases from questions like '除了A外...' / '不包括A'."""
        q = (question or "").strip()
        if not q:
            return []

        terms: list[str] = []

        # 优先提取带引号的排除项
        terms.extend(re.findall(r"除(?:了)?[“\"'‘]([^”\"'’]+)[”\"'’]外", q))

        # 兼容：不包括“xxx” / 不包含“xxx”
        terms.extend(re.findall(r"不(?:包|含)括?[“\"'‘]([^”\"'’]+)[”\"'’]", q))

        # 无引号的兜底
        m = re.search(r"除(?:了)?(.+?)外", q)
        if m:
            raw = str(m.group(1) or "").strip(" ，,。；;：:")
            raw = raw.strip("“”\"'‘’")
            if raw:
                terms.append(raw)

        uniq: list[str] = []
        seen: set[str] = set()
        for t in terms:
            t = str(t or "").strip().strip("“”\"'‘’")
            if not t:
                continue
            if t in seen:
                continue
            seen.add(t)
            uniq.append(t)
        return uniq

    @staticmethod
    def _expand_exclusion_keywords(term: str) -> list[str]:
        """Expand an exclusion phrase into robust matching keywords."""
        s = re.sub(r"\s+", "", str(term or "")).strip()
        if not s:
            return []

        kws: list[str] = [s]

        # 拆分常见分隔符：/、，,；;和及与
        parts = [p.strip() for p in re.split(r"[/、，,；;]|(?:和)|(?:及)|(?:与)", s) if p.strip()]
        kws.extend(parts)

        # 处理“过充/过放未保护”这类共享后缀表达
        if "/" in s and "未保护" in s:
            for p in [x.strip() for x in s.split("/") if x.strip()]:
                if "未保护" not in p:
                    kws.append(p + "未保护")
                if p.endswith("未保护"):
                    kws.append(p[: -len("未保护")])

        # 去重并滤掉无意义短词
        out: list[str] = []
        seen: set[str] = set()
        for k in kws:
            k = str(k or "").strip()
            if len(k) < 2:
                continue
            if k in seen:
                continue
            seen.add(k)
            out.append(k)
        return out

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
