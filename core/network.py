"""HTTP 请求（GET/POST）与 JSONP 解析。"""
import re
import time
import json
import logging
import requests
from config import MAX_RETRIES

log = logging.getLogger(__name__)

_JSONP_RE = re.compile(r'^\s*\w+\s*\((.*)\)\s*;?\s*$', re.DOTALL)

_session = requests.Session()
_session.headers.update({
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/147.0.0.0 Safari/537.36"
    )
})


def get(url, *, headers=None, timeout=12, retries=MAX_RETRIES) -> requests.Response:
    """GET，带超时 + 指数退避重试 + 状态码检查。"""
    for attempt in range(1, retries + 1):
        try:
            r = _session.get(url, headers=headers, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if attempt < retries and status in (429, 502, 503, 504):
                wait = 2 ** attempt
                log.warning("HTTP %d（第 %d 次），%ds 后重试: %s", status, attempt, wait, url)
                time.sleep(wait)
                continue
            raise
        except requests.RequestException as e:
            if attempt == retries:
                raise
            wait = 2 ** attempt
            log.warning("请求失败（第 %d 次），%ds 后重试: %s", attempt, wait, e)
            time.sleep(wait)


def post(url, *, json_data=None, headers=None, timeout=12) -> dict:
    """POST JSON，返回解析后的 dict（失败返回 {}）。"""
    try:
        r = _session.post(url, json=json_data, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.HTTPError as e:
        body = e.response.text[:300] if e.response is not None else ""
        log.warning("POST HTTP %d: %s | body: %s", e.response.status_code, url, body)
        return {"err_code": -1}
    except Exception as e:
        log.warning("POST 失败: %s | %s", url, e)
        return {"err_code": -1}


def parse_jsonp(text: str) -> dict:
    m = _JSONP_RE.match(text)
    if m:
        return json.loads(m.group(1))
    return json.loads(text)
