# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_CSV = "data/磷酸铁锂电池FMECA分析表20250416105822.csv"
DEFAULT_QUESTIONS = "DATA/磷酸铁锂电池Dfmea分析/eval/lfp_dfmea_500_questions.jsonl"
DEFAULT_OUTPUT = "实验/消融实验/磷酸铁锂电池DFMEA"


MODELS = [
    {
        "slug": "Full_全量模型",
        "config": "实验/消融实验/磷酸铁锂电池DFMEA/Full_全量模型/ablation_config.json",
    },
    {"slug": "Full-R0_去除语义优先分流", "config": "实验/消融实验/磷酸铁锂电池DFMEA/Full-R0_去除语义优先分流/ablation_config.json"},
    {"slug": "Full-M3a_去除查询中间表示", "config": "实验/消融实验/磷酸铁锂电池DFMEA/Full-M3a_去除查询中间表示/ablation_config.json"},
    {"slug": "Full-M3b_去除语义检索增强", "config": "实验/消融实验/磷酸铁锂电池DFMEA/Full-M3b_去除语义检索增强/ablation_config.json"},
    {"slug": "Full-Route_固定顺序路由", "config": "实验/消融实验/磷酸铁锂电池DFMEA/Full-Route_固定顺序路由/ablation_config.json"},
    {
        "slug": "Full-M1_去除CSV直答模块",
        "config": "实验/消融实验/磷酸铁锂电池DFMEA/Full-M1_去除CSV直答模块/ablation_config.json",
    },
    {
        "slug": "Full-M2_去除确定性规则问答模块",
        "config": "实验/消融实验/磷酸铁锂电池DFMEA/Full-M2_去除确定性规则问答模块/ablation_config.json",
    },
    {
        "slug": "Full-M3_去除查询理解与检索增强模块",
        "config": "实验/消融实验/磷酸铁锂电池DFMEA/Full-M3_去除查询理解与检索增强模块/ablation_config.json",
    },
    {
        "slug": "Full-M4_去除证据检查与路由裁决模块",
        "config": "实验/消融实验/磷酸铁锂电池DFMEA/Full-M4_去除证据检查与路由裁决模块/ablation_config.json",
    },
    {
        "slug": "Full-SigmaMi_残差模型",
        "config": "实验/消融实验/磷酸铁锂电池DFMEA/Full-SigmaMi_残差模型/ablation_config.json",
    },
    {
        "slug": "Baseline_legacy兼容模型",
        "config": "实验/对比实验/baseline/zenodo_floating_wind_fmea/baseline_config.json",
    },
]


def post_json(url: str, payload: dict, timeout: int = 60) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def wait_port(port: int, timeout: int = 90) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"服务端口 {port} 未在 {timeout} 秒内启动：{last_error}")


def port_is_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=10)
    except ProcessLookupError:
        pass


def start_service(port: int, config: dict, log_path: Path, csv_path: str) -> subprocess.Popen:
    if port_is_open(port):
        raise RuntimeError(f"端口 {port} 已被占用，拒绝复用可能是旧配置的服务。")
    env = os.environ.copy()
    env["KG_RAG_PORT"] = str(port)
    env["DEFAULT_DFMEA_CSV"] = csv_path
    env["FMEA_DEFAULT_CSV"] = csv_path
    for key, value in (config.get("env") or {}).items():
        env[str(key)] = str(value)
    if config.get("model_id") == "baseline":
        env["QA_ENABLE_KG_CHUNK_ANSWER_EXTRACTION"] = "0"
        env["QA_ENABLE_LLM_CYPHER_FALLBACK"] = "1"

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = log_path.open("w", encoding="utf-8")
    base_prefix = Path(os.environ.get("CONDA_PREFIX", "/home/lizhaoxuan/anaconda3"))
    env_python = base_prefix / "envs" / "fmea" / "bin" / "python"
    python_command = str(env_python) if env_python.exists() else sys.executable
    process = subprocess.Popen(
        [python_command, "code/kg_rag.py"],
        cwd=ROOT,
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    wait_port(port)
    return process


def run_one(model: dict, port: int, questions: str, project_csv: str, output_root: Path, timeout: int) -> None:
    config_path = ROOT / model["config"]
    config = json.loads(config_path.read_text(encoding="utf-8"))
    result_dir = output_root / model["slug"] / "实验结果"
    result_dir.mkdir(parents=True, exist_ok=True)
    service_log = result_dir / "服务进程.log"
    process = None
    try:
        print(f"[suite] 启动 {model['slug']}", flush=True)
        process = start_service(port, config, service_log, project_csv)
        base_url = f"http://127.0.0.1:{port}/api/v1"
        post_json(base_url + "/set-top_k", {"top_k": 3}, timeout=60)
        command = [
            sys.executable,
            "scripts/run_scenario_ablation_experiment.py",
            "--base-url",
            base_url,
            "--csv",
            project_csv,
            "--questions",
            questions,
            "--config",
            str(config_path),
            "--output-dir",
            str(result_dir),
            "--top-k",
            "3",
            "--timeout",
            str(timeout),
            "--rebuild-graph",
        ]
        print(f"[suite] 开始 {model['slug']}，题集={questions}", flush=True)
        subprocess.run(command, cwd=ROOT, check=True)
        print(f"[suite] 完成 {model['slug']}", flush=True)
    finally:
        stop_process(process)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run battery DFMEA evaluation suite for Full, ablations, and baseline.")
    parser.add_argument("--port", type=int, default=8092)
    parser.add_argument("--questions", default=DEFAULT_QUESTIONS)
    parser.add_argument("--project-csv", default=DEFAULT_PROJECT_CSV)
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--only", nargs="*", help="只运行指定 slug；不传则运行全部模型。")
    args = parser.parse_args()

    output_root = ROOT / args.output_root
    selected = set(args.only or [])
    models = [m for m in MODELS if not selected or m["slug"] in selected]
    if not models:
        raise SystemExit("没有匹配的模型 slug。")

    for model in models:
        run_one(
            model,
            args.port,
            args.questions,
            args.project_csv,
            output_root,
            args.timeout,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
