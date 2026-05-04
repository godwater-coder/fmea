# -*- coding: utf-8 -*-

# 该文件定义通用响应工具函数，统一构造 API 返回体与状态码。


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
