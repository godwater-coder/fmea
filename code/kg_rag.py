# -*- coding: utf-8 -*-

import connexion
from os import getenv

from kg_rag_core import _as_problem, _json_response
from kg_rag_runtime import get_rag_service
#asproblem 构造统一错误对象

# 接口定义

def create_graph(body: object):
    try:
        path = body.get("path") if isinstance(body, dict) else None
        if not path:
            return _json_response(_as_problem("Bad Request", "缺少字段: path", 400), 400)
        rag = get_rag_service()
        ok = rag.create_fmea_graph(csv_file=path) #建图
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
        result = rag.answer_question(str(question))
        if isinstance(result, dict):
            if "query_ir" not in result:
                try:
                    result["query_ir"] = rag.build_query_ir(str(question)).to_debug_dict() #把问题解释成一个queryIR对象
                except Exception:
                    result["query_ir"] = {}
            result.setdefault("route", "structured") #如果route为空，则置为structured
            result.setdefault("route_confidence", 1.0)
            result.setdefault("missing_slots", [])
        return _json_response(result, 200)
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


def clear_graph(body: object): #用于清空图
    try:
        confirm = body.get("confirm") if isinstance(body, dict) else None
        if confirm is not True: #严格要求只有bool Ture才能通过
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


# 主入口
if __name__ == "__main__":
    app = connexion.FlaskApp(__name__) #创建基于Flask的应用
    app.add_api("api.yml") # 加载后端接口路径
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
            # 旧版 Flask
            application.config["JSON_AS_ASCII"] = json_unicode_escape
    except Exception:
        pass
    app.run(port=8080)
