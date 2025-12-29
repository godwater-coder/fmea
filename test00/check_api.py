#!/usr/bin/env python3
"""
check_api.py - 检查 OpenAI API 可用性的简单脚本

用法:
  1) 在文件顶部替换 API_KEY 的值，或在运行前导出环境变量 `OPENAI_API_KEY`：
       export OPENAI_API_KEY="sk-..."
  2) 运行:
       python3 test00/check_api.py

说明：脚本会按顺序尝试多个模型（首选 `gpt-5.1-codex-max`，失败后回退），并在第一个成功响应时打印预览并退出。
"""

import os
import sys
import json
import requests


# ---------------------------
# 将 API 密钥放在此处仅用于临时测试；强烈建议不要把真实密钥写入源码。
# 推荐做法：不要改动下面的占位符，而是在运行前通过环境变量提供密钥：
#   export OPENAI_API_KEY="sk-..."
# 或者把实际密钥写入此处后在测试完成后立即删除。
API_KEY = "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"
# ---------------------------

# 如果文件中未替换占位符，则从环境变量读取
if API_KEY == "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":
    API_KEY = os.getenv("OPENAI_API_KEY", "")

if not API_KEY:
    print("ERROR: OpenAI API key not provided. Edit this file or set OPENAI_API_KEY environment variable.")
    sys.exit(2)

# 可尝试的模型顺序（按需调整）
MODELS = [
    "gpt-4o-mini",      # 优先使用可用且低延迟的模型
    "gpt-3.5-turbo",
]

ENDPOINT = "https://api.openai.com/v1/chat/completions"

def try_model(model: str) -> bool:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Say hi and identify the model name briefly."}],
        "max_tokens": 32,
    }

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(ENDPOINT, headers=headers, json=payload, timeout=20)
    except requests.exceptions.RequestException as e:
        print(f"Network error for model {model}: {e}")
        return False

    print(f"HTTP status for {model}: {resp.status_code}")

    if 200 <= resp.status_code < 300:
        try:
            data = resp.json()
            content = data.get("choices", [])[0].get("message", {}).get("content", "")
            print("SUCCESS: model responded. Preview:\n")
            print(content)
        except Exception:
            print("SUCCESS but failed to parse JSON. Raw response snippet:\n")
            print(resp.text[:800])
        return True
    else:
        # 更明确地处理常见返回码
        if resp.status_code == 401:
            print("ERROR 401: Invalid API key or unauthorized. Check your key and permissions.")
        elif resp.status_code == 429:
            print("ERROR 429: Rate limited or insufficient quota for this model. Check billing/usage.")
        else:
            print(f"Non-2xx response for {model}. Response snippet:\n{resp.text[:800]}\n")
        return False


def main():
    print("OpenAI API check - trying models:", ", ".join(MODELS))
    for m in MODELS:
        print("\n=== Testing model:", m, "===")
        ok = try_model(m)
        if ok:
            sys.exit(0)

    print("\nAll models attempted and none succeeded. Check API key, account limits, or network connectivity.")
    sys.exit(1)


if __name__ == "__main__":
    main()
