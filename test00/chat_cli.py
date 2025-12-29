#!/usr/bin/env python3
"""Simple CLI chat client using OpenAI Chat Completions API.

Usage:
  export OPENAI_API_KEY="sk-..."
  python3 test00/chat_cli.py

Features:
  - Keeps short in-memory conversation history
  - Uses `requests` to call the public OpenAI endpoint
  - Safe to exit with `quit` or `exit`
"""

import os
import sys
import time
import json
import requests

API_KEY = os.getenv("OPENAI_API_KEY")
if not API_KEY:
    print("ERROR: OPENAI_API_KEY not set. Export it first, e.g.\n  export OPENAI_API_KEY=\"sk-...\"")
    sys.exit(2)

ENDPOINT = "https://api.openai.com/v1/chat/completions"
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def call_openai(messages):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {"model": MODEL, "messages": messages, "max_tokens": 512}
    try:
        resp = requests.post(ENDPOINT, headers=headers, json=payload, timeout=30)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error: {e}")
    if resp.status_code >= 400:
        # bubble up useful error
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        raise RuntimeError(f"HTTP {resp.status_code}: {body}")
    return resp.json()

def main():
    print("Simple CLI Chat — type 'quit' or 'exit' to leave")
    print(f"Using model: {MODEL}")

    # initial system message to guide behavior
    history = [{"role": "system", "content": "You are a helpful assistant."}]

    while True:
        try:
            prompt = input("You: ")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break
        if not prompt:
            continue
        if prompt.strip().lower() in ("quit", "exit"):
            print("Bye")
            break

        # append user message
        history.append({"role": "user", "content": prompt})

        try:
            data = call_openai(history)
        except RuntimeError as e:
            print("Error calling OpenAI:", e)
            # remove last user message so conversation stays consistent
            history.pop()
            time.sleep(1)
            continue

        # extract assistant reply
        try:
            reply = data["choices"][0]["message"]["content"]
        except Exception:
            print("Unexpected response format:")
            print(json.dumps(data)[:1000])
            history.pop()
            continue

        # append assistant message
        history.append({"role": "assistant", "content": reply})

        print("Assistant:")
        print(reply)

if __name__ == "__main__":
    main()
