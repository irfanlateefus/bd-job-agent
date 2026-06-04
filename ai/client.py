"""
Gemini REST client with model auto-fallback on quota exhaustion (429) or
missing model (404). Returns parsed JSON, or {} on failure. Single shared
rate-limit gate keeps us inside the free tier.
"""
import json
import os
import time

import requests

_last_call = 0.0

# Fallback order: cheapest/highest-RPM first, then progressively.
MODEL_FALLBACK = [
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-flash-lite-latest",
]


def generate(prompt: str, model: str = "", rate_limit: float = 7.0,
             max_output_tokens: int = 2048) -> dict:
    """Call Gemini with auto-fallback. Returns parsed JSON dict or {}."""
    global _last_call

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return {}

    elapsed = time.time() - _last_call
    if elapsed < rate_limit:
        time.sleep(rate_limit - elapsed)
    _last_call = time.time()

    models = ([model] + [m for m in MODEL_FALLBACK if m != model]) if model else list(MODEL_FALLBACK)
    # Key travels in a header, never the URL: requests exceptions stringify the
    # full URL, so a key in the query string would leak into logs on any error.
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    for m in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.3,
                "maxOutputTokens": max_output_tokens,
            },
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                return _parse(resp)
            if resp.status_code in (429, 404, 503):
                print(f"  [AI] {m} -> HTTP {resp.status_code}, falling back")
                time.sleep(1)
                continue
            print(f"  [AI] {m} -> HTTP {resp.status_code}, aborting batch")
            return {}
        except requests.RequestException as e:
            # Log the exception class only — never str(e), which can embed the URL.
            print(f"  [AI] {m} -> request error: {type(e).__name__}")
            continue

    return {}


def _parse(resp: requests.Response) -> dict:
    try:
        data = resp.json()
    except ValueError:
        print("  [AI] response body was not JSON")
        return {}

    block = (data.get("promptFeedback") or {}).get("blockReason")
    if block:
        print(f"  [AI] prompt blocked by safety filter: {block}")
        return {}

    candidates = data.get("candidates") or []
    if not candidates:
        print("  [AI] no candidates returned (possible safety block)")
        return {}

    finish = candidates[0].get("finishReason")
    if finish and finish not in ("STOP", "MAX_TOKENS"):
        print(f"  [AI] candidate finishReason={finish}")

    try:
        text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
        return json.loads(text)
    except (json.JSONDecodeError, KeyError, IndexError):
        if finish == "MAX_TOKENS":
            print("  [AI] response truncated at token limit — lower batch_size or raise maxOutputTokens")
        return {}
