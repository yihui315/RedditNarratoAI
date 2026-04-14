"""
src/llm_client.py - 统一 LLM 调用接口
──────────────────────────────────────────────
模型路由:
  qw3.6    → Ollama  (本地)
  gemma4   → Ollama  (本地)
  DeepSeek → DeepSeek API (远程)
  MiniMax  → MiniMax API  (远程, OpenAI兼容)
"""

import os
import re
import json
from typing import Optional, Dict, List, Any

# ── 配置 ──────────────────────────────────────────────────────────────────

OLLAMA_BASE = os.getenv("OLLAMA_BASE", "http://localhost:11434/v1")
OLLAMA_MODELS = ["qw3.6", "gemma4", "llama3", "mixtral"]

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL   = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE    = os.getenv("DEEPSEEK_BASE", "https://api.deepseek.com/v1")

MINIMAX_API_KEY = os.getenv("OPENAI_API_KEY", "")
MINIMAX_MODEL   = os.getenv("MINIMAX_MODEL", "MiniMax-2.7-0628")
MINIMAX_BASE    = os.getenv("OPENAI_API_BASE", "https://api.minimax.chat/v1")


# ── JSON 提取工具 ─────────────────────────────────────────────────────────

def extract_json(text: str) -> Optional[Dict]:
    """从模型输出中提取JSON（处理markdown包裹）"""
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None


# ── Ollama 调用 ─────────────────────────────────────────────────────────────

def call_ollama(
    model: str,
    prompt: str,
    system: str = "",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """
    调用本地 Ollama 模型
    model: qw3.6 / gemma4 / llama3 / mixtral 等
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package required: pip install openai")

    client = OpenAI(api_key="ollama", base_url=OLLAMA_BASE)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


# ── DeepSeek 调用 ──────────────────────────────────────────────────────────

def call_deepseek(
    prompt: str,
    system: str = "",
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """调用 DeepSeek API (OpenAI-compatible)"""
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY not set")

    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package required: pip install openai")

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model or DEEPSEEK_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


# ── MiniMax 调用 ──────────────────────────────────────────────────────────

def call_minimax(
    prompt: str,
    system: str = "",
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> str:
    """调用 MiniMax API (OpenAI-compatible)"""
    if not MINIMAX_API_KEY:
        raise RuntimeError("OPENAI_API_KEY (MiniMax) not set")

    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package required: pip install openai")

    client = OpenAI(api_key=MINIMAX_API_KEY, base_url=MINIMAX_BASE)

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(
        model=model or MINIMAX_MODEL,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


# ── 统一 call 函数（按模型名路由）────────────────────────────────────────────

def call(model_or_provider: str, prompt: str, system: str = "", **kwargs) -> str:
    """
    统一入口，按 model_or_provider 路由到对应后端
    model_or_provider: "qw3.6", "gemma4", "deepseek", "minimax"
    """
    p = model_or_provider.lower()
    if p in OLLAMA_MODELS or p in ["qw3.6", "gemma4", "llama3", "mixtral"]:
        return call_ollama(p, prompt, system, **kwargs)
    elif p in ["deepseek", "deepseek-chat"]:
        return call_deepseek(prompt, system, **kwargs)
    elif p in ["minimax", "minimax-2.7", "minimax-2.7-0628"]:
        return call_minimax(prompt, system, **kwargs)
    else:
        raise ValueError(f"Unknown model/provider: {model_or_provider}")


# ── 结构化输出封装 ─────────────────────────────────────────────────────────

def call_structured(model: str, prompt: str, system: str = "", **kwargs) -> Dict:
    """
    调用并自动提取JSON结果
    返回 dict，失败抛出异常
    """
    text = call(model, prompt, system, **kwargs)
    result = extract_json(text)
    if result is None:
        raise ValueError(f"Failed to extract JSON from model output: {text[:200]}")
    return result
