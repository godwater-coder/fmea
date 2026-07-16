# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import time
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

FMEA_API_BASE = os.getenv("FMEA_API_BASE", "http://127.0.0.1:8080/api/v1").rstrip("/")
FMEA_DEFAULT_CSV = os.getenv("FMEA_DEFAULT_CSV", "data/dfmea_final.csv")
FMEA_TIMEOUT = float(os.getenv("FMEA_TIMEOUT", "90"))
FMEA_BUILD_TIMEOUT = float(os.getenv("FMEA_BUILD_TIMEOUT", "300"))


def _fmea_url(path: str) -> str:
    return f"{FMEA_API_BASE}/{path.lstrip('/')}"


def _read_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


def _problem_payload(title: str, detail: str, status: int) -> dict[str, Any]:
    return {
        "ok": False,
        "type": "about:blank",
        "title": title,
        "detail": detail,
        "status": status,
    }


def _fmea_post(path: str, payload: dict[str, Any], timeout: float | None = None) -> tuple[Any, int]:
    try:
        response = requests.post(_fmea_url(path), json=payload, timeout=timeout or FMEA_TIMEOUT)
    except requests.exceptions.ConnectionError:
        return _problem_payload(
            "FMEA 服务未连接",
            f"无法连接到 {FMEA_API_BASE}。请先在 fmea 目录启动 `python code/kg_rag.py`。",
            502,
        ), 502
    except requests.exceptions.Timeout:
        return _problem_payload("FMEA 服务超时", "请求 FMEA 后端超时，请稍后重试或检查 Neo4j/OpenAI 状态。", 504), 504
    except Exception as exc:
        return _problem_payload("代理异常", str(exc), 500), 500

    body = _read_json(response)
    return body, response.status_code


def _last_user_message(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages or []):
        if message.get("role") in {"user", "human"} and str(message.get("content", "")).strip():
            return str(message["content"]).strip()
    return ""


def _normalize_answer(body: Any, status: int, elapsed_ms: int) -> tuple[dict[str, Any], int]:
    if status >= 400:
        if isinstance(body, dict):
            detail = body.get("detail") or body.get("error") or body.get("message") or str(body)
            title = body.get("title") or "FMEA 请求失败"
            return _problem_payload(str(title), str(detail), status), status
        return _problem_payload("FMEA 请求失败", str(body), status), status

    if isinstance(body, dict):
        answer = body.get("answer") or body.get("content") or body.get("message") or ""
        normalized = {
            "ok": True,
            "answer": answer,
            "content": answer,
            "context": body.get("context", []),
            "context_raw": body.get("context_raw", []),
            "answer_file": body.get("answer_file"),
            "elapsed_ms": elapsed_ms,
            "raw": body,
        }
        return normalized, 200

    return {
        "ok": True,
        "answer": str(body),
        "content": str(body),
        "context": [],
        "context_raw": body,
        "answer_file": None,
        "elapsed_ms": elapsed_ms,
        "raw": body,
    }, 200


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/css/<path:filename>")
def serve_css(filename: str):
    return send_from_directory("css", filename)


@app.route("/js/<path:filename>")
def serve_js(filename: str):
    return send_from_directory("js", filename)


@app.route("/api/status", methods=["GET"])
def status():
    return jsonify(
        {
            "ok": True,
            "app": "DFMEA KG-RAG Workbench",
            "proxy": "ready",
            "fmeaApiBase": FMEA_API_BASE,
            "defaultCsvPath": FMEA_DEFAULT_CSV,
            "timeoutSeconds": FMEA_TIMEOUT,
            "buildTimeoutSeconds": FMEA_BUILD_TIMEOUT,
        }
    )


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    question = str(data.get("question") or "").strip()
    if not question:
        question = _last_user_message(data.get("messages", []))

    if not question:
        return jsonify(_problem_payload("Bad Request", "缺少字段：question", 400)), 400

    top_k = data.get("top_k")
    if top_k not in (None, ""):
        try:
            top_k_value = max(1, int(top_k))
        except Exception:
            return jsonify(_problem_payload("Bad Request", "top_k 必须是正整数", 400)), 400

        top_body, top_status = _fmea_post("set-top_k", {"top_k": top_k_value})
        if top_status >= 400:
            normalized, code = _normalize_answer(top_body, top_status, 0)
            return jsonify(normalized), code

    started = time.perf_counter()
    body, status_code = _fmea_post("question-answer", {"question": question})
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    normalized, code = _normalize_answer(body, status_code, elapsed_ms)
    return jsonify(normalized), code


@app.route("/api/create-graph", methods=["POST"])
def create_graph():
    data = request.get_json(silent=True) or {}
    csv_path = str(data.get("path") or FMEA_DEFAULT_CSV).strip()
    if not csv_path:
        return jsonify(_problem_payload("Bad Request", "缺少字段：path", 400)), 400

    started = time.perf_counter()
    body, status_code = _fmea_post("create-fmea-graph", {"path": csv_path}, timeout=FMEA_BUILD_TIMEOUT)
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if status_code >= 400:
        normalized, code = _normalize_answer(body, status_code, elapsed_ms)
        return jsonify(normalized), code

    return jsonify({"ok": True, "created": bool(body), "path": csv_path, "elapsed_ms": elapsed_ms, "raw": body})


@app.route("/api/clear-graph", methods=["POST"])
def clear_graph():
    data = request.get_json(silent=True) or {}
    if data.get("confirm") is not True:
        return jsonify(_problem_payload("Bad Request", "清空图谱需要 confirm=true", 400)), 400

    body, status_code = _fmea_post("clear-fmea-graph", {"confirm": True}, timeout=FMEA_BUILD_TIMEOUT)
    if status_code >= 400:
        normalized, code = _normalize_answer(body, status_code, 0)
        return jsonify(normalized), code

    return jsonify({"ok": True, "result": body})


@app.route("/api/top-k", methods=["POST"])
def set_top_k():
    data = request.get_json(silent=True) or {}
    try:
        top_k = max(1, int(data.get("top_k")))
    except Exception:
        return jsonify(_problem_payload("Bad Request", "top_k 必须是正整数", 400)), 400

    body, status_code = _fmea_post("set-top_k", {"top_k": top_k})
    if status_code >= 400:
        normalized, code = _normalize_answer(body, status_code, 0)
        return jsonify(normalized), code

    return jsonify({"ok": True, "top_k": top_k, "raw": body})


if __name__ == "__main__":
    print("=" * 64)
    print("DFMEA KG-RAG Workbench")
    print("=" * 64)
    print("Frontend: http://localhost:5000")
    print(f"FMEA API: {FMEA_API_BASE}")
    print(f"Default CSV: {FMEA_DEFAULT_CSV}")
    print("Tip: start the FMEA backend with `python code/kg_rag.py` from the repository root")
    print("=" * 64)
    app.run(host="0.0.0.0", port=5000, debug=True)
