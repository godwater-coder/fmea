# -*- coding: utf-8 -*-

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
    MATCH (fm:FailureMeasure)<-[:isImprovedByFailureMeasure]-(fc:FailureCause)<-[:isDueToFailureCause]-(fd:FailureMode)-[:occursAtProcessStep]->(ps:ProcessStep)
    WITH fm, fc, fd, ps
    MATCH (fd)-[:resultsInFailureEffect]->(fe:FailureEffect)
    WHERE elementId(fd)=$id
    RETURN fm, fc, fe, fd, ps,
           elementId(fm) AS fm_id,
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


def get_failure_measure_ids(repo) -> list[dict]:
    try:
        return repo.query(
            """
            MATCH (fm:FailureMeasure)
            RETURN elementId(fm) AS fm_id;
            """
        )
    except Exception as e:
        print(e)
        return []


def create_chunk(nodes: list[dict]) -> tuple[str, dict]:
    fm, fc, fe, fd, ps = [[] for _ in range(5)]

    node_ids = {
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
            if node.get("fm_id") is not None:
                node_ids["failureMeasureIds"].append(node["fm_id"])

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

    return chunk, node_ids


def create_vector_embeddings(repo) -> bool:
    failure_mode_ids = repo.get_failure_mode_ids()

    repo._ensure_vector_index()

    for entry in failure_mode_ids:
        element_id = entry.get("fd_id")
        if not element_id:
            continue

        nodes = repo.traverse_graph(str(element_id))
        chunk, node_ids = repo.create_chunk(nodes)
        embedded_node_id = repo.add_texts([chunk], metadatas=[node_ids])[0]

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

    return True


def create_fmea_graph(repo, csv_file: str) -> bool:
    repo._ensure_neo4j_available()

    df = repo._read_dfmea_csv(csv_file)
    if df is None:
        return False

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
                properties=repo.format_properties({"ProcessStep": process_step}),
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

        failure_measure = _to_none_if_blank(row.get("FailureMeasure"))
        detection_measure = _to_none_if_blank(row.get("DetectionMeasure"))
        if failure_measure or detection_measure or (d_val is not None and not (isinstance(d_val, float) and pd.isna(d_val))):
            nodes.append(
                MERGE_NODE_QUERY.format(
                    nodeRef="FailureMeasure",
                    node="FailureMeasure",
                    properties=repo.format_properties(
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
            repo.query(query)
        except Exception:
            return False

        inserted_rows += 1

    if inserted_rows == 0:
        return False

    repo.create_vector_embeddings()
    return True
