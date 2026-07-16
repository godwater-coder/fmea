# -*- coding: utf-8 -*-

# 该文件提供服务运维与通用能力，包括 CSV 读取、索引维护、图操作与 LLM 调用工具方法。

from os import getenv
from datetime import datetime
import time
import re
import collections
import json
import os
from pathlib import Path
from types import SimpleNamespace
import requests
import pandas as pd
import graph_building

from synonyms import PROCESS_STEP_SUFFIX_PATTERN
from ..fmea_schema import normalize_to_project_schema
from ..query_ir import QueryConstraint, QueryEntity, QueryIR, QueryScope

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
            root = Path(__file__).resolve().parents[3]
            env_candidates = [
                getenv("DEFAULT_DFMEA_CSV", "").strip(),
                getenv("FMEA_DEFAULT_CSV", "").strip(),
            ]
            for raw in env_candidates:
                if not raw:
                    continue
                p = Path(raw)
                if not p.is_absolute():
                    p = root / raw
                if p.exists():
                    return str(p)

            candidates = [
                root / "data" / "磷酸铁锂电池FMECA分析表20250416105822.csv",
                root / "data" / "dfmea_final.csv",
                root / "data" / "dfmea_std.csv",
            ]
            for p in candidates:
                if p.exists():
                    return str(p)
            return None
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

        return normalize_to_project_schema(df, source_file=csv_file)

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

    def _csv_rows_by_mode(self, mode: str) -> pd.DataFrame | None:
        df = self._get_default_dfmea_df()
        mode_col = "FailureMode" if df is not None and "FailureMode" in df.columns else "潜在失效模式"
        if df is None or mode_col not in df.columns:
            return None
        mode = str(mode or "").strip()
        if not mode:
            return None
        rows = df[df[mode_col].map(lambda x: str(x).strip()) == mode]
        if len(rows):
            return rows
        rows = df[df[mode_col].map(lambda x: mode in str(x).strip() or str(x).strip() in mode)]
        return rows if len(rows) else None

    def _csv_rows_by_code(self, code: str) -> pd.DataFrame | None:
        df = self._get_default_dfmea_df()
        code_col = "FmeaID" if df is not None and "FmeaID" in df.columns else "FMEA编号"
        if df is None or code_col not in df.columns:
            return None
        code = str(code or "").strip()
        if not code:
            return None
        rows = df[df[code_col].map(lambda x: str(x).strip()) == code]
        return rows if len(rows) else None

    @staticmethod
    def _csv_text(row: pd.Series, col: str) -> str:
        if col not in row.index:
            return ""
        value = row.get(col)
        if value is None or pd.isna(value):
            return ""
        s = str(value).strip()
        return "" if s.lower() == "nan" else s

    def _try_answer_basic_csv_lookup(self, question: str) -> dict | None:
        q = str(question or "").strip()
        if not q:
            return None
        quoted = re.findall(r"[“\"'‘]([^”\"'’]+)[”\"'’]", q)
        if not quoted:
            return None

        def yes_no(condition: bool, detail: str) -> dict:
            prefix = "是。" if condition else "否。"
            return {"answer": prefix + detail, "context": ["route=csv_basic"], "context_raw": []}

        def pick(row: pd.Series, *cols: str) -> str:
            for col in cols:
                if col in row.index:
                    return self._csv_text(row, col)
            return ""

        if "FMEA编号" in q and "对应的失效模式" in q:
            rows = self._csv_rows_by_code(quoted[0])
            if rows is None or rows.empty:
                return None
            row = rows.iloc[0]
            mode = pick(row, "FailureMode", "潜在失效模式")
            return {"answer": f"FMEA编号“{quoted[0]}”对应的失效模式是：{mode}。", "context": ["route=csv_basic"], "context_raw": []}

        if "失效模式" not in q:
            return None

        if "项目/功能" in q and "中是否包含失效模式" in q and len(quoted) >= 2:
            project_q = quoted[0]
            mode_q = quoted[1]
            df = self._get_default_dfmea_df()
            if df is None:
                return None
            project_col = "ProcessStep" if "ProcessStep" in df.columns else "项目/功能"
            mode_col = "FailureMode" if "FailureMode" in df.columns else "潜在失效模式"
            matched = df[
                (df[project_col].map(lambda x: str(x).strip()) == project_q)
                & (df[mode_col].map(lambda x: str(x).strip()) == mode_q)
            ]
            return yes_no(not matched.empty, f"项目/功能“{project_q}”{'包含' if not matched.empty else '不包含'}失效模式“{mode_q}”。")

        mode = quoted[0]
        rows = self._csv_rows_by_mode(mode)
        if rows is None or rows.empty:
            return None
        row = rows.iloc[0]
        project = pick(row, "ProcessStep", "项目/功能")
        code = pick(row, "FmeaID", "FMEA编号")
        product = pick(row, "Product", "产品")
        cause = pick(row, "FailureCause", "潜在失效原因/机理")
        effect = pick(row, "FailureEffect", "潜在失效后果")
        prevent = pick(row, "PreventControl", "现行预防控制")
        detect = pick(row, "DetectionMeasure", "现行探测控制")
        action = pick(row, "RecommendedAction", "建议措施", "TempMeasure")
        s_val = pick(row, "S", "严酷度(S)")
        o_val = pick(row, "O", "发生度(O)")
        d_val = pick(row, "D", "可探测度(D)")
        rpn = pick(row, "RPN", "风险优先数(RPN)")

        if "属于哪个项目/功能" in q:
            return {"answer": f"失效模式“{mode}”属于项目/功能“{project}”。", "context": ["route=csv_basic"], "context_raw": []}
        if "对应的FMEA编号" in q:
            return {"answer": f"失效模式“{mode}”对应的FMEA编号是：{code}。", "context": ["route=csv_basic"], "context_raw": []}
        if "潜在失效原因/机理是什么" in q:
            return {"answer": f"失效模式“{mode}”的潜在失效原因/机理是：{cause}。", "context": ["route=csv_basic"], "context_raw": []}
        if "潜在失效后果是什么" in q:
            return {"answer": f"失效模式“{mode}”的潜在失效后果是：{effect}。", "context": ["route=csv_basic"], "context_raw": []}
        if "现行预防控制和现行探测控制分别是什么" in q:
            return {"answer": f"针对失效模式“{mode}”，现行预防控制是：{prevent or '未记录'}；现行探测控制是：{detect or '未记录'}。", "context": ["route=csv_basic"], "context_raw": []}
        if "建议措施是什么" in q:
            return {"answer": f"针对失效模式“{mode}”，建议措施是：{action or '未记录'}。", "context": ["route=csv_basic"], "context_raw": []}
        if "RPN是多少" in q:
            return {"answer": f"失效模式“{mode}”的RPN是：{rpn}。", "context": ["route=csv_basic"], "context_raw": []}
        if "严酷度S是多少" in q:
            return {"answer": f"失效模式“{mode}”的严酷度S是：{s_val}。", "context": ["route=csv_basic"], "context_raw": []}
        if "发生度O是多少" in q:
            return {"answer": f"失效模式“{mode}”的发生度O是：{o_val}。", "context": ["route=csv_basic"], "context_raw": []}
        if "可探测度D是多少" in q:
            return {"answer": f"失效模式“{mode}”的可探测度D是：{d_val}。", "context": ["route=csv_basic"], "context_raw": []}

        if "是否记录了现行预防控制" in q:
            detail = f"失效模式“{mode}”的现行预防控制为“{prevent}”。" if prevent else f"失效模式“{mode}”未记录现行预防控制。"
            return yes_no(bool(prevent), detail)
        if "是否记录了现行探测控制" in q:
            detail = f"失效模式“{mode}”的现行探测控制为“{detect}”。" if detect else f"失效模式“{mode}”未记录现行探测控制。"
            return yes_no(bool(detect), detail)
        if "是否" in q and len(quoted) >= 2:
            target = quoted[1]
            pairs = [
                ("原因是否包含", cause, f"失效模式“{mode}”的潜在失效原因/机理是：{cause}。"),
                ("后果是否为", effect, f"失效模式“{mode}”的潜在失效后果是：{effect}。"),
                ("是否属于", project, f"失效模式“{mode}”所属项目/功能是：{project}。"),
                ("是否来自产品", product, f"失效模式“{mode}”所属产品是：{product}。"),
                ("RPN是否为", rpn, f"失效模式“{mode}”的RPN是：{rpn}。"),
                ("严酷度是否为", s_val, f"失效模式“{mode}”的严酷度S是：{s_val}。"),
                ("发生度是否为", o_val, f"失效模式“{mode}”的发生度O是：{o_val}。"),
                ("可探测度是否为", d_val, f"失效模式“{mode}”的可探测度D是：{d_val}。"),
                ("现行预防控制是否为", prevent, f"失效模式“{mode}”的现行预防控制是：{prevent or '未记录'}。"),
                ("现行探测控制是否为", detect, f"失效模式“{mode}”的现行探测控制是：{detect or '未记录'}。"),
                ("建议措施是否为", action, f"失效模式“{mode}”的建议措施是：{action or '未记录'}。"),
            ]
            for marker, value, detail in pairs:
                if marker in q:
                    normalized = str(value or "").strip()
                    return yes_no(target in normalized if marker == "原因是否包含" else target == normalized, detail)
        return None

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
        expected_dim = self.get_embedding_dimension()
        if expected_dim is None:
            raise RuntimeError(
                "无法确定 embedding 维度：请先确认 Ollama embedding 可用，"
                "且不要使用 DummyEmbeddings。"
            )

        def _index_dimensions() -> int | None:
            try:
                rows = self.query(
                    """
                    SHOW INDEXES YIELD name, type, options
                    WHERE name = $name
                    RETURN options
                    """,
                    params={"name": index_name},
                )
                if not rows:
                    return None
                options = rows[0].get("options") or {}
                cfg = options.get("indexConfig") if isinstance(options, dict) else {}
                if isinstance(cfg, dict):
                    dim = cfg.get("vector.dimensions")
                    return int(dim) if dim is not None else None
            except Exception:
                return None
            return None

        current_dim = _index_dimensions()
        if current_dim is not None and current_dim != expected_dim:
            raise RuntimeError(
                f"向量索引 `{index_name}` 维度不匹配：当前索引={current_dim}，"
                f"当前 embedding={expected_dim}。请先清理旧索引并重新建图。"
            )

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
                cypher = (
                    "CREATE VECTOR INDEX `" + str(index_name).replace("`", "") + "` IF NOT EXISTS "
                    "FOR (n:`" + str(node_label).replace("`", "") + "`) ON (n.`" + str(embedding_prop).replace("`", "") + "`) "
                    "OPTIONS {indexConfig: {`vector.dimensions`: " + str(int(expected_dim)) + ", `vector.similarity_function`: 'cosine'}}"
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
        labels = ["Chunk", "FailureMode", "FailureEffect", "FailureCause", "ProcessStep"]

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
        numeric_keys = {"S", "O", "D", "RPN", "SourceRowNo"}

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
        self.context_qa.append(dict(role="user", content=prompt))

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
        return dict(role="user", content=prompt)

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

    @staticmethod
    def _normalize_query_text(text: str) -> str:
        q = str(text or "").strip()
        q = re.sub(r"\s+", " ", q).strip()
        return q.replace("的的", "的")

    @staticmethod
    def _extract_quoted_values(question: str) -> list[str]:
        return [str(x).strip() for x in re.findall(r"[“\"'‘]([^”\"'’]+)[”\"'’]", question or "") if str(x).strip()]

    def _infer_intent_from_question(self, q: str) -> str:
        metric = self._extract_metric_any(q)
        quoted = self._extract_quoted_values(q)
        has_mode = "失效模式" in q
        has_project = "设计项目" in q or bool(self._extract_process_step_general(q))
        has_avg = "平均" in q
        has_extreme = any(k in q for k in ("最高", "最大", "最低", "最小"))
        has_controls = ("预防性设计控制" in q or "探测性设计控制" in q or "现行预防性设计控制" in q or "现行探测性设计控制" in q)
        has_relation = any(k in q for k in ("原因", "机理", "后果", "影响"))

        if metric and has_mode and quoted:
            return "lookup_metric"
        if metric and has_project and has_avg:
            return "aggregate_metric"
        if metric and has_project and has_extreme and "失效模式" in q:
            return "extreme_metric"
        if "潜在失效模式" in q and has_project:
            return "list_entities"
        if ("是否" in q) and has_mode and len(quoted) >= 2:
            return "boolean_verification"
        if has_mode and quoted and has_controls:
            return "lookup_relation"
        if has_mode and quoted and has_relation:
            return "lookup_relation"
        if quoted or metric or has_project:
            return "semantic_search"
        return "unknown"

    def _extract_entities_from_question(self, q: str) -> list[QueryEntity]:
        entities: list[QueryEntity] = []
        quoted = self._extract_quoted_values(q)
        if "失效模式" in q and quoted:
            entities.append(QueryEntity(kind="failure_mode", value=quoted[0], normalized=quoted[0]))
            if ("是否" in q or "是否为" in q or "是否是" in q) and len(quoted) >= 2:
                tail_kind = "target"
                if "后果" in q or "影响" in q:
                    tail_kind = "effect"
                elif "原因" in q or "机理" in q:
                    tail_kind = "cause"
                entities.append(QueryEntity(kind=tail_kind, value=quoted[-1], normalized=quoted[-1]))
        elif "设计项目" in q and quoted:
            entities.append(QueryEntity(kind="project", value=quoted[0], normalized=quoted[0]))

        scope_step = self._extract_process_step_general(q)
        if scope_step and ("设计项目" in q or "工序" in q or "过程" in q) and not any(e.kind == "project" for e in entities):
            entities.append(QueryEntity(kind="project", value=scope_step, normalized=scope_step))
        return entities

    def _extract_constraints_from_question(self, q: str) -> list[QueryConstraint]:
        constraints: list[QueryConstraint] = []
        ex_terms = self._extract_exclusion_terms(q)
        for term in ex_terms:
            s = str(term or "").strip()
            if not s:
                continue
            constraints.append(QueryConstraint(kind="exclude", operator="!=", value=s))
        return constraints

    def _extract_scope_from_question(self, q: str) -> QueryScope:
        scope = QueryScope()
        if "设计项目" not in q and "工序" not in q and "过程" not in q:
            return scope
        step = self._extract_process_step_general(q)
        if step:
            scope.project = step
            scope.process_step = step
        return scope

    def _infer_output_type(self, ir: QueryIR) -> str:
        if ir.intent == "lookup_metric":
            return "number"
        if ir.intent == "aggregate_metric":
            return "number"
        if ir.intent == "extreme_metric":
            return "set"
        if ir.intent == "list_entities":
            return "set"
        if ir.intent == "boolean_verification":
            return "boolean"
        if ir.intent == "lookup_relation":
            if ir.metric == "controls":
                return "controls_pair"
            return "text"
        if ir.intent == "semantic_search":
            return "text"
        return "unknown"

    def _build_query_variants_from_ir(self, ir: QueryIR) -> list[str]:
        base = self._preprocess_question_for_retrieval(ir.original_question)
        variants = [str(x) for x in (base.get("query_variants") or []) if str(x).strip()]
        if not variants:
            variants = [ir.normalized_question]
        return self._dedupe_keep_order(variants)

    def build_query_ir(self, question: str) -> QueryIR:
        q_norm = self._normalize_query_text(question)
        intent = self._infer_intent_from_question(q_norm)
        entities = self._extract_entities_from_question(q_norm)
        constraints = self._extract_constraints_from_question(q_norm)
        scope = self._extract_scope_from_question(q_norm)
        metric = self._extract_metric_any(q_norm) or ""
        if not metric and ("预防性设计控制" in q_norm or "探测性设计控制" in q_norm):
            metric = "controls"
        if intent == "unknown" and not self.query_ir_strict_mode:
            intent = "semantic_search"
        ir = QueryIR(
            original_question=str(question or "").strip(),
            normalized_question=q_norm,
            intent=intent,
            entities=entities,
            metric=metric,
            constraints=constraints,
            scope=scope,
            confidence=1.0 if intent not in {"semantic_search", "unknown"} else 0.5,
        )
        ir.output_type = self._infer_output_type(ir)
        ir.query_variants = self._build_query_variants_from_ir(ir)
        if not entities:
            ir.notes.append("no_entities")
        if not metric and intent in {"lookup_metric", "aggregate_metric", "extreme_metric"}:
            ir.notes.append("missing_metric")
        return ir

    def _match_failure_mode_name(self, mode_key: str) -> str | None:
        mode_key = str(mode_key or "").strip()
        if not mode_key:
            return None
        rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE fd.FailureMode IS NOT NULL
              AND (toString(fd.FailureMode) = $kw OR toString(fd.FailureMode) CONTAINS $kw OR $kw CONTAINS toString(fd.FailureMode))
            RETURN DISTINCT fd.FailureMode AS FailureMode
            ORDER BY size(toString(fd.FailureMode)) ASC
            LIMIT 5
            """.strip(),
            {"kw": mode_key},
        )
        for row in rows:
            name = str(row.get("FailureMode") or "").strip()
            if name:
                return name
        return None

    def _answer_metric_by_failure_mode(self, mode_name: str, metric: str) -> dict | None:
        if metric not in {"RPN", "S", "O", "D"}:
            return None
        matched = self._match_failure_mode_name(mode_name)
        if not matched:
            return None
        rows = self._query_params(
            f"""
            MATCH (fd:FailureMode)
            WHERE toString(fd.FailureMode) = $mode
              AND fd.{metric} IS NOT NULL
            RETURN toFloat(fd.{metric}) AS v
            LIMIT 1
            """.strip(),
            {"mode": matched},
        )
        if not rows or rows[0].get("v") is None:
            return None
        val = float(rows[0].get("v"))
        metric_name = {"RPN": "RPN", "S": "严重度", "O": "频度数", "D": "探测度数"}.get(metric, metric)
        display = int(val) if float(val).is_integer() else val
        return {
            "answer": f"失效模式“{matched}”的{metric_name}是{display}。",
            "context": [f"FailureMode={matched}", f"metric={metric}"],
            "context_raw": [{"FailureMode": matched, metric: val}],
        }

    def _answer_controls_by_failure_mode_pair(self, mode_name: str) -> dict | None:
        matched = self._match_failure_mode_name(mode_name)
        if not matched:
            return None
        rows = self._query_params(
            """
            MATCH (fd:FailureMode)
            WHERE toString(fd.FailureMode) = $mode
            RETURN DISTINCT
              toString(fd.PreventControl) AS prevent,
              toString(fd.DetectionMeasure) AS detect
            """.strip(),
            {"mode": matched},
        )
        prevent: list[str] = []
        detect: list[str] = []
        for row in rows:
            p = str(row.get("prevent") or "").strip()
            d = str(row.get("detect") or "").strip()
            if p and p.lower() != "nan" and p not in prevent:
                prevent.append(p)
            if d and d.lower() != "nan" and d not in detect:
                detect.append(d)
        if not prevent and not detect:
            return None
        ptxt = "，".join(prevent) if prevent else "未记录"
        dtxt = "，".join(detect) if detect else "未记录"
        return {
            "answer": f"针对“{matched}”，现行预防性设计控制是：{ptxt}；现行探测性设计控制是：{dtxt}。",
            "context": [f"FailureMode={matched}", "relation=controls_pair"],
            "context_raw": [{"FailureMode": matched, "PreventControl": prevent, "DetectionMeasure": detect}],
        }

    def _answer_boolean_relation_by_failure_mode(self, mode_name: str, target_kind: str, target_value: str) -> dict | None:
        matched = self._match_failure_mode_name(mode_name)
        target = str(target_value or "").strip()
        if not matched or not target:
            return None

        if target_kind == "cause":
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)-[:isDueToFailureCause]->(fc:FailureCause)
                WHERE toString(fd.FailureMode) = $mode
                RETURN DISTINCT toString(fc.FailureCause) AS value
                ORDER BY value
                """.strip(),
                {"mode": matched},
            )
            relation_label = "潜在失效原因/机理"
        elif target_kind == "effect":
            rows = self._query_params(
                """
                MATCH (fd:FailureMode)-[:resultsInFailureEffect]->(fe:FailureEffect)
                WHERE toString(fd.FailureMode) = $mode
                RETURN DISTINCT toString(fe.FailureEffect) AS value
                ORDER BY value
                """.strip(),
                {"mode": matched},
            )
            relation_label = "潜在失效后果"
        else:
            return None

        values = [str(r.get("value") or "").strip() for r in rows]
        values = [v for v in values if v and v.lower() != "nan"]
        if not values:
            return None

        yes = any(target in v for v in values)
        prefix = "是。" if yes else "否。"
        answer = f"{prefix}失效模式“{matched}”的{relation_label}包括：" + "；".join(values) + "。"
        return {
            "answer": answer,
            "context": [f"FailureMode={matched}", f"{target_kind}_contains={target}", "lookup=direct"],
            "context_raw": [{"FailureMode": matched, target_kind: values}],
        }

    def build_cypher_from_ir(self, ir: QueryIR) -> str | None:
        if ir.intent == "lookup_metric" and ir.metric in {"RPN", "S", "O", "D"}:
            mode = next((e.value for e in ir.entities if e.kind == "failure_mode" and e.value), "")
            if mode:
                return (
                    "MATCH (fd:FailureMode) "
                    "WHERE toString(fd.FailureMode) CONTAINS $mode "
                    f"RETURN fd.FailureMode AS FailureMode, toFloat(fd.{ir.metric}) AS value "
                    "LIMIT 5"
                )
        if ir.intent == "list_entities" and ir.scope.project:
            return (
                "MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep) "
                "WHERE toString(ps.ProcessStep) CONTAINS $step "
                "RETURN DISTINCT fd.FailureMode AS FailureMode ORDER BY FailureMode"
            )
        return None

    def execute_query_ir(self, ir: QueryIR) -> dict[str, object]:
        if ir.intent == "lookup_metric":
            mode = next((e.value for e in ir.entities if e.kind == "failure_mode"), "")
            if mode and ir.metric:
                ans = self._answer_metric_by_failure_mode(mode, ir.metric)
                if ans is not None:
                    return {
                        "route": "structured",
                        "evidence": ans.get("context", []),
                        "context_raw": ans.get("context_raw", []),
                        "answer_hint": ans.get("answer", ""),
                        "confidence": 1.0,
                        "missing_slots": [],
                    }
            return {"route": "reject", "evidence": [], "context_raw": [], "answer_hint": "", "confidence": 0.0, "missing_slots": ["failure_mode", "metric"]}

        if ir.intent == "lookup_relation" and ir.metric == "controls":
            mode = next((e.value for e in ir.entities if e.kind == "failure_mode"), "")
            if mode:
                ans = self._answer_controls_by_failure_mode_pair(mode)
                if ans is not None:
                    return {
                        "route": "structured",
                        "evidence": ans.get("context", []),
                        "context_raw": ans.get("context_raw", []),
                        "answer_hint": ans.get("answer", ""),
                        "confidence": 1.0,
                        "missing_slots": [],
                    }
            return {"route": "reject", "evidence": [], "context_raw": [], "answer_hint": "", "confidence": 0.0, "missing_slots": ["failure_mode"]}

        if ir.intent == "boolean_verification":
            mode = next((e.value for e in ir.entities if e.kind == "failure_mode"), "")
            target_entity = next((e for e in ir.entities if e.kind in {"cause", "effect"} and e.value), None)
            if mode and target_entity is not None:
                ans = self._answer_boolean_relation_by_failure_mode(mode, target_entity.kind, target_entity.value)
                if ans is not None:
                    return {
                        "route": "structured",
                        "evidence": ans.get("context", []),
                        "context_raw": ans.get("context_raw", []),
                        "answer_hint": ans.get("answer", ""),
                        "confidence": 1.0,
                        "missing_slots": [],
                    }
            missing = ["failure_mode"]
            if not target_entity:
                missing.append("target")
            return {"route": "reject", "evidence": [], "context_raw": [], "answer_hint": "", "confidence": 0.0, "missing_slots": missing}

        if ir.intent in {"semantic_search", "unknown", "boolean_verification", "list_entities", "aggregate_metric", "extreme_metric", "lookup_relation"}:
            cypher = self.build_cypher_from_ir(ir)
            if cypher:
                try:
                    params: dict[str, object] = {}
                    if ir.scope.project:
                        params["step"] = ir.scope.project
                    mode = next((e.value for e in ir.entities if e.kind == "failure_mode"), "")
                    if mode:
                        params["mode"] = mode
                    rows = self._query_params(cypher, params)
                    if rows:
                        return {
                            "route": "graph",
                            "evidence": rows,
                            "context_raw": rows,
                            "answer_hint": "",
                            "confidence": 0.8,
                            "missing_slots": [],
                        }
                except Exception:
                    pass
            return {
                "route": "vector",
                "evidence": [],
                "context_raw": [],
                "answer_hint": "",
                "confidence": 0.5,
                "missing_slots": [],
            }

        return {
            "route": "reject",
            "evidence": [],
            "context_raw": [],
            "answer_hint": "",
            "confidence": 0.0,
            "missing_slots": ["intent"],
        }

    @staticmethod
    def _normalize_evidence_value(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            if value.is_integer():
                return str(int(value))
            return f"{value:.6f}".rstrip("0").rstrip(".")
        if isinstance(value, int):
            return str(value)
        if isinstance(value, (list, tuple, set)):
            items = [str(x).strip() for x in value if str(x).strip()]
            return " | ".join(items)
        return str(value).strip()

    def _extract_evidence_claims(self, ir: QueryIR, execution_result: dict[str, object]) -> dict[str, set[str]]:
        claims: dict[str, set[str]] = {}
        rows = execution_result.get("context_raw") or []
        if not isinstance(rows, list):
            rows = [rows]

        if ir.intent == "lookup_metric":
            mode = next((e.normalized or e.value for e in ir.entities if e.kind == "failure_mode"), "")
            metric = str(ir.metric or "").strip()
            if not metric:
                return claims
            key = f"lookup_metric:{mode}:{metric}"
            for row in rows:
                if not isinstance(row, dict):
                    continue
                value = row.get(metric)
                if value is None:
                    value = row.get("value")
                if value is None:
                    value = row.get("v")
                normalized = self._normalize_evidence_value(value)
                if normalized:
                    claims.setdefault(key, set()).add(normalized)
            return claims

        if ir.intent == "lookup_relation" and ir.metric == "controls":
            mode = next((e.normalized or e.value for e in ir.entities if e.kind == "failure_mode"), "")
            key = f"lookup_relation:{mode}:controls"
            for row in rows:
                if not isinstance(row, dict):
                    continue
                prevent = self._normalize_evidence_value(row.get("PreventControl") or row.get("prevent"))
                detect = self._normalize_evidence_value(row.get("DetectionMeasure") or row.get("detect"))
                normalized = f"prevent={prevent};detect={detect}"
                if prevent or detect:
                    claims.setdefault(key, set()).add(normalized)
            return claims

        if ir.intent == "boolean_verification":
            mode = next((e.normalized or e.value for e in ir.entities if e.kind == "failure_mode"), "")
            target_entity = next((e for e in ir.entities if e.kind in {"cause", "effect"} and (e.normalized or e.value)), None)
            if not mode or target_entity is None:
                return claims
            key = f"boolean_verification:{mode}:{target_entity.kind}"
            for row in rows:
                if not isinstance(row, dict):
                    continue
                value = row.get(target_entity.kind)
                normalized = self._normalize_evidence_value(value)
                if normalized:
                    claims.setdefault(key, set()).add(normalized)
            return claims

        return claims

    def _detect_evidence_conflicts(self, ir: QueryIR, execution_result: dict[str, object]) -> list[dict[str, object]]:
        conflicts: list[dict[str, object]] = []
        claims = self._extract_evidence_claims(ir, execution_result)
        for claim_key, values in claims.items():
            normalized_values = sorted(v for v in values if v)
            if len(normalized_values) > 1:
                conflicts.append({"claim": claim_key, "values": normalized_values})
        return conflicts

    def _adjudicate_execution_result(self, ir: QueryIR, execution_result: dict[str, object]) -> dict[str, object]:
        route = str(execution_result.get("route") or "reject")
        answer_hint = str(execution_result.get("answer_hint") or "").strip()
        evidence = execution_result.get("evidence") or []
        context_raw = execution_result.get("context_raw") or []
        missing_slots = [str(x) for x in (execution_result.get("missing_slots") or []) if str(x).strip()]
        conflicts = self._detect_evidence_conflicts(ir, execution_result)
        has_raw_evidence = bool(context_raw)
        has_any_evidence = bool(evidence) or has_raw_evidence

        if conflicts:
            return {
                "status": "reject",
                "reason": "evidence_conflict",
                "route": route,
                "conflicts": conflicts,
                "missing_slots": missing_slots,
            }

        if route == "structured":
            if answer_hint and has_raw_evidence:
                return {
                    "status": "answered",
                    "reason": "structured_evidence_confirmed",
                    "route": route,
                    "conflicts": [],
                    "missing_slots": missing_slots,
                }
            return {
                "status": "pending",
                "reason": "structured_evidence_insufficient",
                "route": route,
                "conflicts": [],
                "missing_slots": missing_slots,
            }

        if route == "graph":
            if has_raw_evidence:
                return {
                    "status": "answered",
                    "reason": "graph_evidence_confirmed",
                    "route": route,
                    "conflicts": [],
                    "missing_slots": missing_slots,
                }
            return {
                "status": "pending",
                "reason": "graph_evidence_insufficient",
                "route": route,
                "conflicts": [],
                "missing_slots": missing_slots,
            }

        if route == "vector":
            return {
                "status": "pending",
                "reason": "vector_candidate_only",
                "route": route,
                "conflicts": [],
                "missing_slots": missing_slots,
            }

        if missing_slots:
            return {
                "status": "pending",
                "reason": "missing_slots",
                "route": route,
                "conflicts": [],
                "missing_slots": missing_slots,
            }

        if has_any_evidence:
            return {
                "status": "pending",
                "reason": "evidence_insufficient",
                "route": route,
                "conflicts": [],
                "missing_slots": missing_slots,
            }

        return {
            "status": "pending",
            "reason": "no_evidence",
            "route": route,
            "conflicts": [],
            "missing_slots": missing_slots,
        }

    def _compose_pending_confirmation_text(
        self,
        ir: QueryIR,
        adjudication: dict[str, object],
        candidate_evidence: list[str] | None = None,
    ) -> str:
        reason = str(adjudication.get("reason") or "")
        missing_slots = [str(x) for x in (adjudication.get("missing_slots") or []) if str(x).strip()]
        conflicts = adjudication.get("conflicts") or []
        source = str(adjudication.get("route") or "unknown")
        prefix = "待确认："

        if reason == "evidence_conflict" and conflicts:
            first = conflicts[0]
            values = " / ".join(str(x) for x in (first.get("values") or [])[:3])
            return f"{prefix}证据存在冲突，当前拒绝直接作答。冲突项={first.get('claim')}，候选值={values}。"

        if missing_slots:
            return f"{prefix}证据不足，缺少关键约束：{', '.join(missing_slots)}。"

        if reason == "vector_candidate_only":
            if candidate_evidence:
                return f"{prefix}当前仅命中文本候选证据，尚不能作为最终结论。候选证据：{'；'.join(candidate_evidence[:3])}。"
            return f"{prefix}当前仅命中文本候选证据，尚不能作为最终结论。"

        if source == "graph":
            return f"{prefix}已命中图关系证据，但不足以形成唯一结论。"

        if source == "structured":
            return f"{prefix}已命中结构化字段，但证据不完整，暂不生成结论。"

        return f"{prefix}证据不足，暂不生成结论。"

    def _compose_graph_answer(self, ir: QueryIR, query_result: list[object]) -> tuple[str, list[str]]:
        if ir.intent == "lookup_metric":
            metric_name = {"RPN": "RPN", "S": "严重度", "O": "频度数", "D": "探测度数"}.get(ir.metric, ir.metric)
            for row in query_result:
                if not isinstance(row, dict):
                    continue
                mode = str(row.get("FailureMode") or "").strip()
                value = row.get("value")
                if value is None:
                    value = row.get(ir.metric)
                normalized = self._normalize_evidence_value(value)
                if mode and normalized:
                    return f"失效模式“{mode}”的{metric_name}是{normalized}。", [f"FailureMode={mode}", f"metric={ir.metric}"]

        if ir.intent == "list_entities":
            items: list[str] = []
            for row in query_result:
                if not isinstance(row, dict):
                    continue
                for field in ("FailureMode", "ProcessStep", "project", "name", "value"):
                    value = str(row.get(field) or "").strip()
                    if value and value not in items:
                        items.append(value)
                        break
            if items:
                if ir.scope.project:
                    return f"“{ir.scope.project}”相关条目包括：" + "，".join(items) + "。", items
                return "相关条目包括：" + "，".join(items) + "。", items

        pre_answer: list[str] = []
        for r in query_result:
            result_summarize = self.run_inference(
                [self.summarize_context(context=json.dumps(r, ensure_ascii=False), question=ir.original_question)]
            )
            summarized = self._normalize_llm_answer_text(result_summarize.choices[0].message.content)
            if summarized:
                pre_answer.append(summarized)
        answer_context = self._format_context_for_answer(query_result)
        if not answer_context:
            answer_context = json.dumps(pre_answer, ensure_ascii=False)
        self.qa_prompt_context(ir.original_question, answer_context)
        answer = self.run_inference(list(self.context_qa), temperature=0.0)
        answer_text = self._normalize_llm_answer_text(answer.choices[0].message.content) or "；".join(pre_answer) or "抱歉，未找到可用答案。"
        return answer_text, pre_answer

    def _collect_vector_candidate_evidence(self, ir: QueryIR) -> tuple[list[str], list[object]]:
        prep = {
            "original": ir.original_question,
            "normalized": ir.normalized_question,
            "rag_query": ir.query_variants[0] if ir.query_variants else ir.normalized_question,
            "query_variants": ir.query_variants,
            "metric": ir.metric,
            "slot": "",
            "exclusion_terms": [c.value for c in ir.constraints if c.kind == "exclude"],
        }
        query_variants = [str(x) for x in (prep.get("query_variants") or []) if str(x).strip()]
        if not query_variants:
            query_variants = [str(prep.get("rag_query") or ir.original_question or "").strip()]

        self._ensure_vector_index()
        query_result = self._vector_search_multi_queries(query_variants, k=self.top_k)
        candidate_evidence: list[str] = []
        for r in query_result:
            try:
                result_summarize = self.run_inference(
                    [self.summarize_context(context=json.dumps(r, ensure_ascii=False), question=ir.original_question)]
                )
                summarized = self._normalize_llm_answer_text(result_summarize.choices[0].message.content)
            except Exception:
                summarized = ""
            if summarized:
                candidate_evidence.append(summarized)
                continue
            raw = self._format_context_for_answer([r]).strip()
            if raw:
                candidate_evidence.append(raw)
        return candidate_evidence, query_result

    def compose_answer_from_ir(self, ir: QueryIR, execution_result: dict[str, object]) -> dict:
        route = str(execution_result.get("route") or "reject")
        route_confidence = float(execution_result.get("confidence") or 0.0)
        missing_slots = [str(x) for x in (execution_result.get("missing_slots") or []) if str(x).strip()]
        adjudication = self._adjudicate_execution_result(ir, execution_result)
        adjudication_conflicts = adjudication.get("conflicts") or []

        if adjudication.get("status") == "answered" and route == "structured":
            answer_text = str(execution_result.get("answer_hint") or "").strip() or "抱歉，未找到可用答案。"
            answer_file = self._save_answer_to_file(answer_text)
            return {
                "answer": answer_text,
                "answer_file": answer_file,
                "context": [str(x) for x in (execution_result.get("evidence") or [])],
                "context_raw": execution_result.get("context_raw") or [],
                "query_ir": ir.to_debug_dict(),
                "route": route,
                "route_confidence": route_confidence,
                "missing_slots": missing_slots,
                "adjudication": adjudication,
            }

        if adjudication.get("status") == "answered" and route == "graph":
            query_result = execution_result.get("context_raw") or []
            answer_text, pre_answer = self._compose_graph_answer(ir, query_result)
            answer_file = self._save_answer_to_file(answer_text)
            return {
                "answer": answer_text,
                "answer_file": answer_file,
                "context": pre_answer,
                "context_raw": query_result,
                "query_ir": ir.to_debug_dict(),
                "route": route,
                "route_confidence": route_confidence,
                "missing_slots": missing_slots,
                "adjudication": adjudication,
            }

        candidate_evidence: list[str] = []
        candidate_raw: list[object] = []
        if route == "vector":
            try:
                candidate_evidence, candidate_raw = self._collect_vector_candidate_evidence(ir)
            except Exception as e:
                candidate_evidence = [f"vector_candidate_error={e}"]

        answer_text = self._compose_pending_confirmation_text(
            ir,
            adjudication,
            candidate_evidence=candidate_evidence,
        )
        answer_file = self._save_answer_to_file(answer_text)
        return {
            "answer": answer_text,
            "answer_file": answer_file,
            "context": candidate_evidence if candidate_evidence else [str(x) for x in (execution_result.get("evidence") or [])],
            "context_raw": candidate_raw if candidate_raw else (execution_result.get("context_raw") or []),
            "query_ir": ir.to_debug_dict(),
            "route": route,
            "route_confidence": route_confidence,
            "missing_slots": missing_slots,
            "adjudication": adjudication,
            "evidence_conflicts": adjudication_conflicts,
        }

    def _preprocess_question_for_retrieval(self, question: str) -> dict[str, object]:
        """Normalize and rewrite question for vector retrieval before QA routing."""
        q = str(question or "").strip()
        q_norm = self._normalize_query_text(q)
        q_norm = q_norm.replace("是什么？", "是什么？")
        variants: list[str] = [q_norm]
        if q_norm != q:
            variants.append(q_norm)

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

        # 对“是否为/是否是”类问题，显式保留肯定/否定对象，减少模型把比较语气吞掉。
        bool_match = re.search(r"失效模式[“\"'‘](.+?)[”\"'’].*?(?:是否为|是否是)[“\"'‘](.+?)[”\"'’]", q_norm)
        if bool_match:
            mode = bool_match.group(1).strip()
            target = bool_match.group(2).strip()
            variants.append(f"判断失效模式“{mode}”的后果是否是“{target}”，只回答是或不是。")

        # 对排除语义做显式改写，提升向量检索召回准确度。
        ex_terms = self._extract_exclusion_terms(q_norm)
        if ex_terms:
            variants.append(f"{q_norm}。注意排除：{'，'.join(ex_terms)}。")

        variants = self._dedupe_keep_order(variants)
        if len(variants) > self.query_rewrite_count:
            variants = variants[: self.query_rewrite_count]

        # 尽量把更短、更明确的表达排在前面，提升向量召回和 Cypher 生成稳定性。
        variants.sort(key=len)

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

    @staticmethod
    def _normalize_llm_answer_text(text: str) -> str:
        s = str(text or "").strip()
        s = re.sub(r"^\s*<\|im_start\|>.*?\n", "", s, flags=re.S).strip()
        s = re.sub(r"^\s*(总结|回答|助手|Assistant|AI)[:：]\s*", "", s).strip()
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @staticmethod
    def _format_context_for_answer(query_result: list[object]) -> str:
        parts: list[str] = []
        for i, r in enumerate(query_result, start=1):
            if isinstance(r, dict):
                items = []
                for k, v in r.items():
                    if v is None:
                        continue
                    if isinstance(v, (list, tuple, set)):
                        v = "；".join(str(x) for x in v if str(x).strip())
                    items.append(f"{k}={v}")
                if items:
                    parts.append(f"[{i}] " + ", ".join(items))
            else:
                t = str(getattr(r, "page_content", r) or "").strip()
                if t:
                    parts.append(f"[{i}] {t}")
        return "\n".join(parts)

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

        # 对检索结果做结构化压缩，再用于最终回答。
        for r in query_result:
            result_summarize = self.run_inference(
                [self.summarize_context(context=json.dumps(r, ensure_ascii=False), question=question_original)]
            )
            summarized = self._normalize_llm_answer_text(result_summarize.choices[0].message.content)
            if summarized:
                pre_answer.append(summarized)
            else:
                raw = self._format_context_for_answer([r]).strip()
                if raw:
                    pre_answer.append(raw)

        answer_context = self._format_context_for_answer(query_result)
        if not answer_context:
            answer_context = json.dumps(pre_answer, ensure_ascii=False)
        self.qa_prompt_context(question_original, answer_context)
        qa_temp_raw = (getenv("OLLAMA_QA_TEMPERATURE", "0") or "0").strip()
        try:
            qa_temp = float(qa_temp_raw)
        except Exception:
            qa_temp = 0.0
        answer = self.run_inference(list(self.context_qa), temperature=qa_temp)

        answer_text = self._normalize_llm_answer_text(answer.choices[0].message.content)
        if not answer_text:
            fallback_parts = [str(x).strip() for x in pre_answer if str(x).strip()]
            answer_text = "；".join(fallback_parts) if fallback_parts else "抱歉，未找到可用答案。"
        if answer_text.startswith("总结："):
            answer_text = answer_text[len("总结："):].strip()
        answer_file = self._save_answer_to_file(answer_text)

        return {
            "answer": answer_text,
            "answer_file": answer_file,
            "context": pre_answer,
            "context_raw": query_result,
        }

    # 最关键的“直接调用大模型 API”的函数：它把 messages=context 发给 Ollama 的原生 chat 接口，
    # 默认指向本地 Ollama，再把模型返回的补全结果对象原样返回。
    # 参数：context(list[dict])、temperature(float)、max_tokens(int)；返回：聊天补全结果对象；功能：调用 LLM 接口让模型基于上下文生成内容。
    def run_inference(
        self, context: list[dict], temperature: float = 0.0, max_tokens: int = 4000
    ):
        """
            调用 Ollama 原生 chat 接口进行推理。

        Args:
            context (list): 消息上下文列表（每项为 dict，包含 role/content 等字段）。
            temperature (float): 生成随机性，越大越发散。
            max_tokens (int): 最大生成 token 数。

        Returns:
            object: 聊天补全结果对象（可通过 choices[0].message.content 取文本）。
        """
        model = getenv("OLLAMA_MODEL", "qwen2.5:7b")
        api_base = getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434"
        resp = requests.post(
            f"{api_base.rstrip('/')}/api/chat",
            json={
                "model": model,
                "messages": context,
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
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )

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

        # 优先支持显式引号项目名：设计项目“X”中... / 项目“X”的...
        quoted = re.findall(r"[“\"]([^”\"]+)[”\"]", q)
        if quoted:
            for cand in quoted:
                ps = cls._normalize_process_step_name(cand)
                if ps:
                    return ps

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
