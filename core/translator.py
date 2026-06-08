"""Gemini API 日→中 翻译，多模型池 + RPM 冷却 + 自动降级。"""
import time
import logging
import requests
from config import GEMINI_API_KEY, GEMINI_MODELS

log = logging.getLogger(__name__)

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
PROMPT = (
    "将以下日文博客翻译成简体中文，按中日参照格式逐段输出。要求：\n"
    "1. 保持原文的语气和风格，人名保留日文原文不翻译\n"
    "2. 每个段落先输出中文译文，再输出日文原文，方便对照阅读\n"
    "3. 格式严格如下：\n"
    "【中文】\n（该段的中文翻译）\n【原文】\n（该段的日文原文）\n\n"
    "4. 段落之间用空行分隔，不要添加任何额外解释或前言\n"
    "5. 整体开头不要加标题或说明，直接从第一段【中文】开始\n\n"
)

_cooldown: dict[str, float] = {}


def _available_models() -> list[dict]:
    """返回当前未在冷却中的模型列表（保持配置顺序）。"""
    now = time.time()
    return [m for m in GEMINI_MODELS if _cooldown.get(m["name"], 0) <= now]


def translate(text: str) -> str:
    if not GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY 未配置，跳过翻译")
        return ""
    if not GEMINI_MODELS:
        log.warning("GEMINI_MODELS 为空，跳过翻译")
        return ""

    models = _available_models()
    if not models:
        wait = min(_cooldown.get(m["name"], 0) for m in GEMINI_MODELS) - time.time()
        log.warning("所有模型都在冷却中，%.0fs 后恢复", max(wait, 0))
        return ""

    for model in models:
        url = f"{API_BASE}/{model['name']}:generateContent?key={GEMINI_API_KEY}"
        try:
            r = requests.post(
                url,
                json={"contents": [{"parts": [{"text": PROMPT + text}]}]},
                timeout=60,
            )
            r.raise_for_status()
            data = r.json()
            result = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            _cooldown[model["name"]] = time.time() + 60.0 / model["rpm"]
            log.debug("翻译成功: %s", model["name"])
            return result
        except Exception as e:
            log.warning("翻译失败 [%s]: %s", model["name"], e)
            continue

    log.warning("所有模型翻译均失败")
    return ""
