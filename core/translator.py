"""Gemini API 日→中 翻译，多模型池 + RPM 冷却 + 自动降级。"""
import time
import logging
import requests
from config import GEMINI_API_KEY, GEMINI_MODELS

log = logging.getLogger(__name__)

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
PROMPT = (
    "将以下日文博客翻译成中文。要求："
    "保持原文的语气和风格，人名保留日文原文不翻译，"
    "只输出译文，不要添加任何解释。\n\n"
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
