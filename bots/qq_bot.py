"""QQ Bot：Token 缓存、文字/图片推送。"""
import re
import time
import threading
import logging
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from config import BOTS, get_blacklist, QQ_API_BASE, IMAGE_SEND_DELAY
from core.network import post

log = logging.getLogger(__name__)

_token_cache: dict[str, tuple[str, float]] = {}
_token_lock = threading.Lock()


def _get_access_token(app_id: str, client_secret: str) -> str | None:
    with _token_lock:
        cached = _token_cache.get(app_id)
        if cached and time.time() < cached[1] - 60:
            return cached[0]
    data = post("https://bots.qq.com/app/getAppAccessToken",
                json_data={"appId": app_id, "clientSecret": client_secret})
    token = data.get("access_token")
    expires = int(data.get("expires_in", 7200))
    if token:
        with _token_lock:
            _token_cache[app_id] = (token, time.time() + expires)
        log.debug("Token 已刷新: appId=%s", app_id)
    return token


def _bot_headers(token: str) -> dict:
    return {"Authorization": f"QQBot {token}", "Content-Type": "application/json"}


def _send_text(token: str, openid: str, group: str,
               author: str, title: str, blog_url: str, img_count: int,
               blog_date: str = "") -> bool:
    emoji = "🌸" if "樱" in group else "☀️" if "日" in group else "💜" if "乃" in group else "🤖"
    date_line = f"**时间**：{blog_date}\n" if blog_date else ""
    md_text = (
        f"{emoji} **{group} 博客更新**\n\n"
        f"**作者**：{author}\n"
        f"**标题**：{title}\n"
        f"{date_line}"
        f"**照片**：共 {img_count} 张\n\n"
        f"👉 **博客链接**：\n{blog_url}"
    )
    url = f"{QQ_API_BASE}/v2/users/{openid}/messages"
    headers = _bot_headers(token)
    resp = post(url, json_data={"msg_type": 2, "markdown": {"content": md_text}}, headers=headers)
    if resp.get("err_code", 0) == 0:
        return True
    plain = (
        f"{emoji} {group} 博客更新\n"
        f"作者：{author}\n标题：{title}\n"
        + (f"时间：{blog_date}\n" if blog_date else "")
        + f"照片：共 {img_count} 张\n"
        f"👉 链接：\n{blog_url}"
    )
    resp2 = post(url, json_data={"msg_type": 0, "content": plain}, headers=headers)
    return resp2.get("err_code", 0) == 0


def _send_image(token: str, openid: str, image_url: str,
                retries: int = 3, retry_delay: float = 2.0) -> bool:
    headers    = _bot_headers(token)
    upload_url = f"{QQ_API_BASE}/v2/users/{openid}/files"
    msg_url    = f"{QQ_API_BASE}/v2/users/{openid}/messages"
    fname      = image_url.split("/")[-1]

    for attempt in range(1, retries + 1):
        resp = post(upload_url,
                    json_data={"file_type": 1, "url": image_url, "srv_send_msg": False},
                    headers=headers, timeout=15)
        file_info = resp.get("file_info")
        if not file_info:
            err = resp.get("message") or resp.get("err_code") or "无响应"
            if attempt < retries:
                log.warning("图片上传失败（第%d次）%s → %s，%.0fs后重试",
                            attempt, fname, err, retry_delay * attempt)
                time.sleep(retry_delay * attempt)
                continue
            else:
                log.warning("图片上传彻底失败（已重试%d次）%s → %s", retries, fname, err)
                return False

        send_resp = post(msg_url,
                         json_data={"msg_type": 7, "media": {"file_info": file_info}},
                         headers=headers)
        err_code = send_resp.get("err_code", 0)
        if err_code == 0:
            return True
        else:
            err_msg = send_resp.get("message", "未知错误")
            if attempt < retries:
                log.warning("图片发送失败（第%d次）%s → [%s] %s，%.0fs后重试",
                            attempt, fname, err_code, err_msg, retry_delay * attempt)
                time.sleep(retry_delay * attempt)
            else:
                log.warning("图片发送彻底失败（已重试%d次）%s → [%s] %s",
                            retries, fname, err_code, err_msg)
                return False
    return False


def _fmt_translation_qq(text: str) -> str:
    """中日参照文本 → QQ Markdown：中文段落粗体、日文段落斜体，移除【中文】/【原文】标签。"""
    blocks = []
    current_type = None
    current_lines: list[str] = []

    for line in text.split('\n'):
        if line == '【中文】':
            if current_type and current_lines:
                content = '\n'.join(current_lines).strip()
                blocks.append(f'**{content}**' if current_type == 'zh' else f'*{content}*')
            current_type = 'zh'
            current_lines = []
        elif line == '【原文】':
            if current_type and current_lines:
                content = '\n'.join(current_lines).strip()
                blocks.append(f'**{content}**' if current_type == 'zh' else f'*{content}*')
            current_type = 'ja'
            current_lines = []
        else:
            current_lines.append(line)

    if current_type and current_lines:
        content = '\n'.join(current_lines).strip()
        blocks.append(f'**{content}**' if current_type == 'zh' else f'*{content}*')

    return '\n\n'.join(blocks)


def _push_to_single_bot(bot: dict, group_key: str, group: str,
                        author: str, title: str, blog_url: str,
                        images: list[str], blog_date: str,
                        body_zh_future: Future | None) -> dict:
    """推送到单个 QQ Bot，返回结果字典（成功信息由调用方统一汇总）。"""
    result = {
        "bot": bot["name"],
        "text_ok": False,
        "images_ok": 0,
        "images_total": len(images),
        "tr_ok": None,
        "skipped": False,
        "skip_reason": "",
    }

    if not bot["groups"].get(group_key, True):
        result["skipped"] = True
        result["skip_reason"] = f"已关闭 {group} 推送"
        return result
    if author in get_blacklist(bot_name=bot["name"]):
        result["skipped"] = True
        result["skip_reason"] = f"{author} 在黑名单中"
        return result

    log.info("  ▶ 推送到 [%s] ...", bot["name"])
    token = _get_access_token(bot["app_id"], bot["client_secret"])
    if not token:
        log.warning("  ✗ Token 获取失败，跳过 [%s]", bot["name"])
        result["skipped"] = True
        result["skip_reason"] = "Token 获取失败"
        return result

    result["text_ok"] = _send_text(token, bot["target_openid"], group, author, title,
                                   blog_url, len(images), blog_date)

    ok_count = 0
    for idx, img_url in enumerate(images, 1):
        if _send_image(token, bot["target_openid"], img_url):
            ok_count += 1
        else:
            log.warning("图片推送失败 [%s] 第%d张: %s", bot["name"], idx, img_url)
        time.sleep(IMAGE_SEND_DELAY)
    result["images_ok"] = ok_count
    if images and ok_count != len(images):
        log.warning("  ⚠ 图片推送不完整 %d/%d → [%s]", ok_count, len(images), bot["name"])

    # 翻译文本 — 等待 Future 就绪
    body_zh = ""
    if body_zh_future is not None:
        try:
            body_zh = body_zh_future.result()
        except Exception as e:
            log.warning("翻译 Future 异常 [%s]: %s", bot["name"], e)

    if body_zh:
        url = f"{QQ_API_BASE}/v2/users/{bot['target_openid']}/messages"
        headers = _bot_headers(token)
        md_body = _fmt_translation_qq(body_zh)
        resp = post(url, json_data={"msg_type": 2, "markdown": {"content": md_body}},
                    headers=headers)
        err = resp.get("err_code")
        if err is not None and err != 0:
            log.warning("翻译 Markdown 推送失败 [%s]: err_code=%s message=%s，回退纯文本",
                        bot["name"], err, resp.get("message", ""))
            resp = post(url, json_data={"msg_type": 0, "content": body_zh},
                        headers=headers)
            err = resp.get("err_code")
        tr_ok = err is None or err == 0
        if not tr_ok:
            log.warning("翻译推送彻底失败 [%s]: err_code=%s message=%s",
                        bot["name"], err, resp.get("message", ""))
        result["tr_ok"] = tr_ok

    return result


def push_to_all(group_key: str, group: str, author: str, title: str,
                blog_url: str, images: list[str], blog_date: str = "",
                body_zh_future: Future | None = None) -> tuple[bool, list[dict]]:
    """并行推送到所有 QQ Bot，返回 (是否有至少一个 Bot 文字通知成功, 各 Bot 结果列表)。"""
    from config import QQ_ENABLED
    if not QQ_ENABLED:
        log.info("QQ Bot 总开关已关闭，跳过推送")
        return False, []

    if not BOTS:
        return False, []

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=len(BOTS)) as pool:
        futures = {
            pool.submit(_push_to_single_bot, bot, group_key, group,
                       author, title, blog_url, images, blog_date,
                       body_zh_future): bot
            for bot in BOTS
        }
        for f in as_completed(futures):
            bot = futures[f]
            try:
                results.append(f.result())
            except Exception as e:
                log.warning("  ✗ [%s] 推送异常: %s", bot["name"], e)
                results.append({
                    "bot": bot["name"],
                    "text_ok": False,
                    "images_ok": 0,
                    "images_total": len(images),
                    "tr_ok": None,
                    "skipped": True,
                    "skip_reason": f"异常: {e}",
                })

    # 按 BOTS 配置顺序排序
    bot_order = {b["name"]: i for i, b in enumerate(BOTS)}
    results.sort(key=lambda r: bot_order.get(r["bot"], 999))
    any_ok = any(r["text_ok"] for r in results)
    return any_ok, results
