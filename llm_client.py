"""LLM client, OpenAI SDK compatible."""

from __future__ import annotations

import json
import os
import yaml
from pathlib import Path

_CONFIG_LOCAL = Path(__file__).parent / "config.local.yaml"
_CONFIG_PATH = Path(__file__).parent / "config.yaml"
DEFAULT_LLM_CONFIG = {
    "provider": "deepseek",
    "model": "deepseek-v4-flash",
    "base_url": "https://api.deepseek.com",
    "api_key": "${DEEPSEEK_API_KEY}",
    "max_tokens": 4096,
    "temperature": 0.7,
}


def _load_config() -> dict:
    path = _CONFIG_LOCAL if _CONFIG_LOCAL.exists() else _CONFIG_PATH
    if not path.exists():
        return {"llm": dict(DEFAULT_LLM_CONFIG)}
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    llm = dict(DEFAULT_LLM_CONFIG)
    llm.update(cfg.get("llm") or {})
    cfg["llm"] = llm
    return cfg


def get_config_source() -> str:
    """Return which config file is active."""
    if _CONFIG_LOCAL.exists():
        return str(_CONFIG_LOCAL)
    if _CONFIG_PATH.exists():
        return str(_CONFIG_PATH)
    return "built-in DeepSeek defaults"


def _resolve_secret(value: str) -> str:
    """Resolve env-style secret placeholders without committing keys."""
    if not value:
        return ""
    value = str(value).strip()
    if value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    if value.startswith("env:"):
        return os.getenv(value[4:], "")
    return value


def get_client() -> OpenAI:
    from openai import OpenAI

    cfg = _load_config()["llm"]
    api_key = _resolve_secret(cfg.get("api_key", ""))
    if not api_key or api_key.startswith("YOUR_"):
        raise ValueError("LLM API Key 未配置，请设置 config.local.yaml 或对应环境变量。")
    return OpenAI(api_key=api_key, base_url=cfg["base_url"])


def get_llm_config() -> dict:
    """Return non-secret LLM config for UI/status display."""
    cfg = dict(_load_config().get("llm", {}))
    raw_key = _resolve_secret(cfg.get("api_key", ""))
    cfg["config_source"] = get_config_source()
    cfg["api_key_configured"] = bool(raw_key and not raw_key.startswith("YOUR_"))
    cfg["api_key"] = _mask_key(raw_key) if raw_key else ""
    return cfg


def test_llm_connection() -> dict:
    """Make a tiny DeepSeek call and return a safe status payload."""
    cfg = get_llm_config()
    try:
        text = chat("请只回复 OK。", system="你是连通性测试助手。", max_tokens=8, temperature=0)
        return {
            "ok": True,
            "provider": cfg.get("provider"),
            "model": cfg.get("model"),
            "base_url": cfg.get("base_url"),
            "message": text.strip(),
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": cfg.get("provider"),
            "model": cfg.get("model"),
            "base_url": cfg.get("base_url"),
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }


def chat(
    prompt: str,
    *,
    system: str = "你是一个专业的AI求职助手。",
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    response_format: dict | None = None,
) -> str:
    cfg = _load_config()["llm"]
    client = get_client()

    kwargs: dict = {
        "model": model or cfg["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature if temperature is not None else cfg["temperature"],
        "max_tokens": max_tokens or cfg["max_tokens"],
    }
    if response_format:
        kwargs["response_format"] = response_format

    resp = client.chat.completions.create(**kwargs)
    content = resp.choices[0].message.content or ""
    import re
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return content


def chat_json(prompt: str, *, system: str = "你是一个专业的AI求职助手。回复必须是合法JSON，不要包含任何其他内容。") -> dict:
    text = chat(prompt, system=system)
    text = _extract_json(text)
    return json.loads(text)


def _extract_json(text: str) -> str:
    """Strip think tags, markdown fences, and other noise to extract pure JSON."""
    import re
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = text.strip()
    if "```" in text:
        lines = text.split("\n")
        inside = False
        json_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                inside = not inside
                continue
            if inside:
                json_lines.append(line)
        if json_lines:
            text = "\n".join(json_lines)
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1:
        text = text[brace_start : brace_end + 1]
    return text.strip()


def _mask_key(value: str) -> str:
    value = str(value or "")
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}***{value[-4:]}"
