"""QQ Bot：Token 缓存、文字/图片推送。"""
import time
import logging
from config import BOTS, QQ_API_BASE, IMAGE_SEND_DELAY, BOT_SWITCH_DELAY
from core.network import post

log = logging.getLogger(__name__)

_token_cache: dict[str, tuple[str, float]] = {}


def _get_access_token(app_id: str, client_secret: str) -> str | None:
    cached = _token_cache.get(app_id)
    if cached and time.time() < cached[1] - 60:
        return cached[0]
    data = post("https://bots.qq.com/app/getAppAccessToken",
                json_data={"appId": app_id, "clientSecret": client_secret})
    token = data.get("access_token")
    expires = int(data.get("expires_in", 7200))
    if token:
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


def push_to_all(group_key: str, group: str, author: str, title: str,
                blog_url: str, images: list[str], blog_date: str = "") -> bool:
    """推送到所有 Bot，返回是否有至少一个 Bot 文字通知成功。"""
    from config import QQ_ENABLED
    if not QQ_ENABLED:
        log.info("QQ Bot 总开关已关闭，跳过推送")
        return False
    any_ok = False
    for bi, bot in enumerate(BOTS):
        if not bot["groups"].get(group_key, True):
            log.info("  ⏭ [%s] 已关闭 %s 推送，跳过", bot["name"], group)
            continue
        if bi > 0:
            time.sleep(BOT_SWITCH_DELAY)
        log.info("  ▶ 推送到 [%s] ...", bot["name"])
        token = _get_access_token(bot["app_id"], bot["client_secret"])
        if not token:
            log.warning("  ✗ Token 获取失败，跳过 [%s]", bot["name"])
            continue
        ok = _send_text(token, bot["target_openid"], group, author, title,
                        blog_url, len(images), blog_date)
        log.info("  %s 文字通知 → [%s]", "✓" if ok else "✗", bot["name"])
        if ok:
            any_ok = True
        ok_count = 0
        for idx, img_url in enumerate(images, 1):
            if _send_image(token, bot["target_openid"], img_url):
                ok_count += 1
            else:
                log.warning("图片推送失败 [%s] 第%d张: %s", bot["name"], idx, img_url)
            time.sleep(IMAGE_SEND_DELAY)
        if images:
            if ok_count == len(images):
                log.info("  ✓ 图片全部推送成功 %d/%d → [%s]", ok_count, len(images), bot["name"])
            else:
                log.warning("  ⚠ 图片推送不完整 %d/%d → [%s]", ok_count, len(images), bot["name"])
    return any_ok
