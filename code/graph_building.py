# -*- coding: utf-8 -*-

import re

import pandas as pd


MERGE_NODE_QUERY = "MERGE ({nodeRef}:{node} {properties})"
MERGE_RELATION_QUERY = "MERGE ({nodeRef1})-[:{relation}]->({nodeRef2})"
MATCH_QUERY = "MATCH ({nodeRef}:{node} {properties})"


def _query_with_params(repo, cypher: str, params: dict) -> list[dict]:
    try:
        return repo.query(cypher, params=params)
    except TypeError:
        rendered = cypher
        for k, v in params.items():
            safe = str(v).replace("\\", "\\\\").replace("'", "\\'")
            rendered = rendered.replace("$" + k, "'" + safe + "'")
        return repo.query(rendered)


def traverse_graph(repo, failure_mode_element_id: str) -> list[dict]:
    query = """
    MATCH (fd:FailureMode)
    WHERE elementId(fd)=$id
    MATCH (fd)-[:occursAtProcessStep]->(ps:ProcessStep)
    OPTIONAL MATCH (fd)-[:isDueToFailureCause]->(fc:FailureCause)
    OPTIONAL MATCH (fd)-[:resultsInFailureEffect]->(fe:FailureEffect)
    RETURN fc, fe, fd, ps,
           elementId(fc) AS fc_id,
           elementId(fe) AS fe_id,
           elementId(fd) AS fd_id,
           elementId(ps) AS ps_id;
    """
    try:
        return _query_with_params(repo, query, {"id": str(failure_mode_element_id)})
    except Exception as e:
        print(e)
        return []


def get_failure_mode_ids(repo) -> list[dict]:
    try:
        return repo.query(
            """
            MATCH (fd:FailureMode)
            RETURN elementId(fd) AS fd_id;
            """
        )
    except Exception as e:
        print(e)
        return []

def create_chunk(nodes: list[dict]) -> tuple[str, dict]:
    fc, fe, fd, ps = [[] for _ in range(4)]

    node_ids = {
        "failureModeIds": [],
        "failureEffectIds": [],
        "failureCauseIds": [],
        "processStepIds": [],
    }

    for node in nodes:
        fc_node = node.get("fc")
        if fc_node is not None and fc_node not in fc:
            fc.append(fc_node)
            if node.get("fc_id") is not None:
                node_ids["failureCauseIds"].append(node["fc_id"])

        fe_node = node.get("fe")
        if fe_node is not None and fe_node not in fe:
            fe.append(fe_node)
            if node.get("fe_id") is not None:
                node_ids["failureEffectIds"].append(node["fe_id"])

        fd_node = node.get("fd")
        if fd_node is not None and fd_node not in fd:
            fd.append(fd_node)
            if node.get("fd_id") is not None:
                node_ids["failureModeIds"].append(node["fd_id"])

        ps_node = node.get("ps")
        if ps_node is not None and ps_node not in ps:
            ps.append(ps_node)
            if node.get("ps_id") is not None:
                node_ids["processStepIds"].append(node["ps_id"])

    def _get_str(d: object, key: str) -> str:
        if not isinstance(d, dict):
            return ""
        v = d.get(key)
        if v is None:
            return ""
        return str(v)

    def _unique_text(nodes_: list[object], key: str) -> list[str]:
        out: list[str] = []
        for item in nodes_:
            value = _get_str(item, key).strip()
            if value and value.lower() != "nan" and value not in out:
                out.append(value)
        return out

    mode = fd[0] if fd else {}
    fmea_id = _get_str(mode, "FmeaID").strip()
    failure_mode = _get_str(mode, "FailureMode").strip()
    rpn = _get_str(mode, "RPN").strip()
    s_val = _get_str(mode, "S").strip()
    o_val = _get_str(mode, "O").strip()
    d_val = _get_str(mode, "D").strip()
    prevent = _get_str(mode, "PreventControl").strip()
    detect = _get_str(mode, "DetectionMeasure").strip()
    action = _get_str(mode, "RecommendedAction").strip() or _get_str(mode, "TempMeasure").strip()
    process_steps = _unique_text(ps, "ProcessStep")
    causes = _unique_text(fc, "FailureCause")
    effects = _unique_text(fe, "FailureEffect")

    lines = [
        "FMEA knowledge graph evidence chunk.",
        "This chunk is generated from one FailureMode node and its graph neighbours.",
        f"FMEA编号 / FmeaID / record id / 编号: {fmea_id}",
        f"项目/功能 / ProcessStep / where it happens / 哪一块 / 哪个地方: {'；'.join(process_steps)}",
        f"失效模式 / FailureMode / problem / issue / 毛病 / 啥问题 / 什么坏: {failure_mode}",
        f"风险优先数 / RPN / risk score / 风险数 / 危险分 / 分数: {rpn}",
        f"严重度 / S / severity: {s_val}",
        f"发生度 / O / occurrence: {o_val}",
        f"可探测度 / D / detection / 能查出来的分: {d_val}",
        f"失效原因 / FailureCause / cause / reason / 为什么 / 为啥 / 咋来的: {'；'.join(causes)}",
        f"失效后果 / FailureEffect / effect / result / consequence / 结果 / 后果 / 会怎样: {'；'.join(effects)}",
        f"现行预防控制 / PreventControl: {prevent}",
        f"现行探测控制 / DetectionMeasure: {detect}",
        f"建议措施 / RecommendedAction / action / 怎么处理 / 咋处理: {action}",
        "Graph relations: FailureMode occursAtProcessStep ProcessStep; FailureMode isDueToFailureCause FailureCause; FailureMode resultsInFailureEffect FailureEffect.",
    ]
    chunk = "\n".join(line for line in lines if line.strip())

    return chunk, node_ids


def create_vector_embeddings(repo) -> bool:
    failure_mode_ids = repo.get_failure_mode_ids()

    repo._ensure_vector_index()

    def _embed_text(text: str) -> list[float]:
        embedding = getattr(repo, "embedding", None) or getattr(repo, "_embedding", None)
        if embedding is None:
            raise RuntimeError("未找到 embedding 实例")
        return embedding.embed_query(text)

    for offset, entry in enumerate(failure_mode_ids, start=1):
        element_id = entry.get("fd_id")
        if not element_id:
            continue

        nodes = repo.traverse_graph(str(element_id))
        chunk, node_ids = repo.create_chunk(nodes)
        embedded_node_id = f"fmea_chunk_{offset}_{element_id}"
        embedded_node_id = str(embedded_node_id).replace(":", "_")

        _query_with_params(
            repo,
            """
            MERGE (index:Chunk {id: $id})
            SET index.text = $text,
                index.embedding = $embedding,
                index.failureModeIds = $failureModeIds,
                index.failureEffectIds = $failureEffectIds,
                index.failureCauseIds = $failureCauseIds,
                index.processStepIds = $processStepIds
            """,
            {
                "id": embedded_node_id,
                "text": chunk,
                "embedding": _embed_text(chunk),
                "failureModeIds": node_ids.get("failureModeIds", []),
                "failureEffectIds": node_ids.get("failureEffectIds", []),
                "failureCauseIds": node_ids.get("failureCauseIds", []),
                "processStepIds": node_ids.get("processStepIds", []),
            },
        )

        query = [
            MATCH_QUERY.format(
                nodeRef="index",
                node="Chunk",
                properties=repo.format_properties({"id": embedded_node_id}),
            ),
            "WITH index ",
            MATCH_QUERY.format(
                nodeRef="fd",
                node="FailureMode",
                properties=repo.format_properties({}),
            ),
            "WHERE elementId(fd)=$id",
            MERGE_RELATION_QUERY.format(
                nodeRef1="fd",
                relation="isIndexed",
                nodeRef2="index",
            ),
        ]

        _query_with_params(repo, "\n".join(query), {"id": str(element_id)})

    def _fmt_num(value: object) -> str:
        try:
            n = float(value)
        except Exception:
            return str(value or "")
        return str(int(n)) if n.is_integer() else f"{n:.2f}".rstrip("0").rstrip(".")

    def _upsert_summary_chunk(chunk_id: str, text: str) -> None:
        if not text.strip():
            return
        _query_with_params(
            repo,
            """
            MERGE (index:Chunk {id: $id})
            SET index.text = $text,
                index.embedding = $embedding,
                index.chunkType = "kg_summary"
            """,
            {"id": chunk_id, "text": text, "embedding": _embed_text(text)},
        )

    try:
        top_rows = _query_with_params(
            repo,
            """
            MATCH (fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
            OPTIONAL MATCH (fd)-[:isDueToFailureCause]->(fc:FailureCause)
            OPTIONAL MATCH (fd)-[:resultsInFailureEffect]->(fe:FailureEffect)
            WITH fd, ps,
                 collect(DISTINCT fc.FailureCause) AS causes,
                 collect(DISTINCT fe.FailureEffect) AS effects,
                 toFloat(fd.RPN) AS rpn
            WHERE rpn IS NOT NULL
            RETURN fd.FmeaID AS fmeaId,
                   ps.ProcessStep AS processStep,
                   fd.FailureMode AS failureMode,
                   rpn AS rpn,
                   fd.S AS s,
                   fd.O AS o,
                   fd.D AS d,
                   causes AS causes,
                   effects AS effects,
                   fd.RecommendedAction AS recommendedAction,
                   fd.TempMeasure AS tempMeasure
            ORDER BY rpn DESC
            LIMIT 20
            """,
            {},
        )
    except Exception:
        top_rows = []

    if top_rows:
        lines = [
            "FMEA knowledge graph summary chunk.",
            "主题: 全局最高RPN / top risk / 最麻烦 / 最该担心 / 优先看 / 高分。",
            "用途: 回答哪条风险最高、先处理哪个、最高风险的失效模式原因后果和建议措施。",
        ]
        for idx, row in enumerate(top_rows, start=1):
            action = row.get("recommendedAction") or row.get("tempMeasure") or "未记录"
            causes = "；".join(str(x) for x in row.get("causes") or [] if str(x).strip())
            effects = "；".join(str(x) for x in row.get("effects") or [] if str(x).strip())
            lines.append(
                f"排名{idx}: FMEA编号={row.get('fmeaId')}; 项目/功能={row.get('processStep')}; "
                f"失效模式={row.get('failureMode')}; RPN={_fmt_num(row.get('rpn'))}; "
                f"S={_fmt_num(row.get('s'))}; O={_fmt_num(row.get('o'))}; D={_fmt_num(row.get('d'))}; "
                f"原因={causes or '未记录'}; 后果={effects or '未记录'}; 建议措施={action}."
            )
        _upsert_summary_chunk("fmea_summary_global_top_rpn", "\n".join(lines))

    try:
        project_rows = _query_with_params(
            repo,
            """
            MATCH (ps:ProcessStep)<-[:occursAtProcessStep]-(fd:FailureMode)
            OPTIONAL MATCH (fd)-[:isDueToFailureCause]->(fc:FailureCause)
            OPTIONAL MATCH (fd)-[:resultsInFailureEffect]->(fe:FailureEffect)
            WITH ps, fd,
                 collect(DISTINCT fc.FailureCause) AS causes,
                 collect(DISTINCT fe.FailureEffect) AS effects,
                 toFloat(fd.RPN) AS rpn
            WHERE rpn IS NOT NULL
            ORDER BY ps.ProcessStep, rpn DESC
            WITH ps,
                 count(fd) AS total,
                 avg(rpn) AS avgRpn,
                 avg(toFloat(fd.S)) AS avgS,
                 avg(toFloat(fd.O)) AS avgO,
                 avg(toFloat(fd.D)) AS avgD,
                 max(rpn) AS maxRpn,
                 collect({
                    fmeaId: fd.FmeaID,
                    failureMode: fd.FailureMode,
                    rpn: rpn,
                    s: fd.S,
                    o: fd.O,
                    d: fd.D,
                    causes: causes,
                    effects: effects,
                    recommendedAction: fd.RecommendedAction,
                    tempMeasure: fd.TempMeasure
                 })[..5] AS topModes
            RETURN ps.ProcessStep AS processStep,
                   total AS total,
                   avgRpn AS avgRpn,
                   avgS AS avgS,
                   avgO AS avgO,
                   avgD AS avgD,
                   maxRpn AS maxRpn,
                   topModes AS topModes
            ORDER BY ps.ProcessStep
            """,
            {},
        )
    except Exception:
        project_rows = []

    for idx, row in enumerate(project_rows, start=1):
        process_step = str(row.get("processStep") or "").strip()
        if not process_step:
            continue
        lines = [
            "FMEA knowledge graph project summary chunk.",
            f"项目/功能 / ProcessStep / 哪一块 / 哪个地方: {process_step}",
            f"记录数量 / count / 多少条: {_fmt_num(row.get('total'))}",
            f"平均RPN / average risk score / 平均风险分: {_fmt_num(row.get('avgRpn'))}",
            f"平均严重度 / average S / severity: {_fmt_num(row.get('avgS'))}",
            f"平均发生度 / average O / occurrence: {_fmt_num(row.get('avgO'))}",
            f"平均可探测度 / average D / detection / 平均能查出来的那个分: {_fmt_num(row.get('avgD'))}",
            f"最高RPN / top risk / 最麻烦 / 最该担心 / 优先看: {_fmt_num(row.get('maxRpn'))}",
            "项目内最高风险条目:",
        ]
        for rank, top in enumerate(row.get("topModes") or [], start=1):
            action = top.get("recommendedAction") or top.get("tempMeasure") or "未记录"
            causes = "；".join(str(x) for x in top.get("causes") or [] if str(x).strip())
            effects = "；".join(str(x) for x in top.get("effects") or [] if str(x).strip())
            lines.append(
                f"排名{rank}: FMEA编号={top.get('fmeaId')}; 失效模式={top.get('failureMode')}; "
                f"RPN={_fmt_num(top.get('rpn'))}; S={_fmt_num(top.get('s'))}; "
                f"O={_fmt_num(top.get('o'))}; D={_fmt_num(top.get('d'))}; "
                f"原因={causes or '未记录'}; 后果={effects or '未记录'}; 建议措施={action}."
            )
        safe_id = re.sub(r"[^0-9A-Za-z_\-]+", "_", process_step).strip("_")[:80] or str(idx)
        _upsert_summary_chunk(f"fmea_summary_process_{idx}_{safe_id}", "\n".join(lines))

    return True


def create_fmea_graph(repo, csv_file: str) -> bool:
    repo._ensure_neo4j_available()
    try:
        repo.clear_fmea_graph()
    except Exception:
        pass

    df = repo._read_dfmea_csv(csv_file)
    if df is None:
        return False

    if "FailureMode" not in df.columns or "ProcessStep" not in df.columns:
        return False

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

    inserted_rows = 0
    for _, row in df.iterrows():
        failure_mode = _to_none_if_blank(row.get("FailureMode"))
        process_step = _to_none_if_blank(row.get("ProcessStep"))
        if not failure_mode or not process_step:
            continue

        prevent_control = _to_none_if_blank(row.get("PreventControl"))
        detect_control = _to_none_if_blank(row.get("DetectionMeasure"))
        recommended_action = _to_none_if_blank(row.get("RecommendedAction"))
        temp_measure = _to_none_if_blank(row.get("TempMeasure"))
        action_priority = _to_none_if_blank(row.get("ActionPriority"))
        action_status = _to_none_if_blank(row.get("ActionStatus"))
        action_result = _to_none_if_blank(row.get("ActionResult"))
        remark = _to_none_if_blank(row.get("Remark"))
        fmea_id = _to_none_if_blank(row.get("FmeaID"))
        product = _to_none_if_blank(row.get("Product"))
        analysis_level = _to_none_if_blank(row.get("AnalysisLevel"))
        domain = _to_none_if_blank(row.get("Domain"))
        dataset_id = _to_none_if_blank(row.get("DatasetID"))
        project_id = _to_none_if_blank(row.get("ProjectID"))
        schema_version = _to_none_if_blank(row.get("SchemaVersion"))
        source_file = _to_none_if_blank(row.get("SourceFile"))
        source_row_no = row.get("SourceRowNo")
        import_batch_id = _to_none_if_blank(row.get("ImportBatchID"))

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
                properties=repo.format_properties(
                    {
                        "ProcessStep": process_step,
                        "Product": product,
                        "AnalysisLevel": analysis_level,
                        "Domain": domain,
                        "DatasetID": dataset_id,
                        "ProjectID": project_id,
                        "SchemaVersion": schema_version,                    }
                ),
            )
        )

        nodes.append(
            MERGE_NODE_QUERY.format(
                nodeRef="FailureMode",
                node="FailureMode",
                properties=repo.format_properties(
                    {
                        "FailureMode": failure_mode,
                        "RPN": rpn,
                        "S": s_val,
                        "O": o_val,
                        "D": d_val,
                        "PreventControl": prevent_control,
                        "DetectionMeasure": detect_control,
                        "RecommendedAction": recommended_action,
                        "TempMeasure": temp_measure,
                        "ActionPriority": action_priority,
                        "ActionStatus": action_status,
                        "ActionResult": action_result,
                        "Remark": remark,
                        "FmeaID": fmea_id,
                        "Product": product,
                        "AnalysisLevel": analysis_level,
                        "Domain": domain,
                        "DatasetID": dataset_id,
                        "ProjectID": project_id,
                        "SchemaVersion": schema_version,
                        "SourceFile": source_file,
                        "SourceRowNo": source_row_no,
                        "ImportBatchID": import_batch_id,
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
                    properties=repo.format_properties({"FailureEffect": failure_effect, "S": s_val}),
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
                    properties=repo.format_properties({"FailureCause": failure_cause, "O": o_val}),
                )
            )
            relations.append(
                MERGE_RELATION_QUERY.format(
                    nodeRef1="FailureMode",
                    relation="isDueToFailureCause",
                    nodeRef2="FailureCause",
                )
            )

        query = "\n".join(nodes + relations)

        try:
            repo.query(query)
        except Exception:
            return False

        inserted_rows += 1

    if inserted_rows == 0:
        return False

    repo.create_vector_embeddings()
    return True
