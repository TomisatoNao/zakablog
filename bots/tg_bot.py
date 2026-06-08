"""Telegram Bot：文本/媒体组推送，一个坂道一个机器人。"""
import asyncio
import html as _html
import logging
import re
from concurrent.futures import Future
from config import TG_ENABLED, TG_GROUPS, get_blacklist, MAX_RETRIES

log = logging.getLogger(__name__)


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def _retry_wait(exc: Exception) -> float:
    """从异常中提取 retry_after（含少量余量），无法提取则返回 0 表示调用方自定。"""
    retry_attr = getattr(exc, 'retry_after', None)
    if retry_attr is not None:
        return float(retry_attr) + 0.5
    import re
    m = re.search(r'Retry in (\d+(?:\.\d+)?)', str(exc))
    if m:
        return float(m.group(1)) + 0.5
    return 0.0


def _fmt_translation_tg(text: str) -> str:
    """中日参照文本 → Telegram HTML：中文段落粗体、日文段落斜体，移除去【中文】/【原文】标签，段内去空行。"""
    blocks = []
    current_type = None
    current_lines: list[str] = []

    for line in text.split('\n'):
        if line == '【中文】':
            if current_type and current_lines:
                content = '\n'.join(current_lines).strip()
                content = re.sub(r'\n{2,}', '\n', content)  # 段内去空行
                content = _html.escape(content)
                blocks.append(f'<b>{content}</b>' if current_type == 'zh' else f'<i>{content}</i>')
            current_type = 'zh'
            current_lines = []
        elif line == '【原文】':
            if current_type and current_lines:
                content = '\n'.join(current_lines).strip()
                content = re.sub(r'\n{2,}', '\n', content)
                content = _html.escape(content)
                blocks.append(f'<b>{content}</b>' if current_type == 'zh' else f'<i>{content}</i>')
            current_type = 'ja'
            current_lines = []
        else:
            current_lines.append(line)

    if current_type and current_lines:
        content = '\n'.join(current_lines).strip()
        content = re.sub(r'\n{2,}', '\n', content)
        content = _html.escape(content)
        blocks.append(f'<b>{content}</b>' if current_type == 'zh' else f'<i>{content}</i>')

    # 原文+译文成对紧挨，对与对之间空一行
    result = []
    for i in range(0, len(blocks), 2):
        pair = blocks[i:i+2]
        result.append('\n'.join(pair))
    return '\n\n'.join(result)


async def _push_async(token: str, chat_id: str, group_name: str,
                      author: str, title: str, blog_url: str,
                      images: list[str], blog_date: str = "",
                      body_zh_future: Future | None = None) -> dict:
    try:
        from telegram import Bot, InputMediaPhoto
        from telegram.constants import ParseMode
        from telegram.error import RetryAfter, TimedOut
        from telegram.request import HTTPXRequest
    except ImportError:
        log.warning("python-telegram-bot 未安装，跳过 Telegram 推送")
        return False

    request = HTTPXRequest(read_timeout=120, connect_timeout=10, write_timeout=60)
    bot = Bot(token=token, request=request)
    emoji = "🌸" if "樱" in group_name else "☀️" if "日" in group_name else "💜" if "乃" in group_name else "🤖"

    date_line = f"<b>时间</b>：{blog_date}\n" if blog_date else ""
    img_note = f"<b>照片</b>：共 {len(images)} 张\n\n" if images else "\n"
    html_text = (
        f"{emoji} <b>{group_name} 博客更新</b>\n\n"
        f"<b>作者</b>：{author}\n"
        f"<b>标题</b>：{title}\n"
        f"{date_line}"
        f"{img_note}"
        f"👉 <a href=\"{blog_url}\">博客链接</a>"
    )

    result = {
        "main_ok": False,
        "images_ok": 0,
        "images_total": len(images),
        "batch_count": 0,
        "tr_ok": None,
    }

    # 无图片：纯文字
    if not images:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await bot.send_message(chat_id=chat_id, text=html_text,
                                       parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                result["main_ok"] = True
                break
            except TimedOut:
                log.warning("Telegram 推送超时 [%s]（服务端可能已收到），视为成功", group_name)
                result["main_ok"] = True
                break
            except Exception as e:
                if attempt < MAX_RETRIES:
                    wait = _retry_wait(e) or (2 ** attempt)
                    log.warning("Telegram 推送失败 [%s] 第%d次: %s，%.1fs后重试",
                                group_name, attempt, e, wait)
                    await asyncio.sleep(wait)
                else:
                    log.warning("  ✗ Telegram 推送失败 [%s]（已重试%d次）: %s",
                                group_name, MAX_RETRIES, e)

    else:
        # 有图片：第一张带 HTML 摘要，≤10 张/组
        batches = list(_chunks(images, 10))
        result["batch_count"] = len(batches)
        ok_count = 0
        any_explicit_fail = False
        for bi, batch in enumerate(batches):
            caption = html_text if bi == 0 else ""
            media = []
            for i, url in enumerate(batch):
                if bi == 0 and i == 0:
                    media.append(InputMediaPhoto(media=url, caption=caption,
                                                 parse_mode=ParseMode.HTML))
                else:
                    media.append(InputMediaPhoto(media=url))
            sent = False
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    await bot.send_media_group(chat_id=chat_id, media=media)
                    ok_count += len(batch)
                    sent = True
                    break
                except TimedOut:
                    log.warning("Telegram 媒体组超时 [%s] 第%d组（服务端可能已收到），视为成功",
                                group_name, bi + 1)
                    ok_count += len(batch)
                    sent = True
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES:
                        wait = _retry_wait(e) or (2 ** attempt)
                        log.warning("Telegram 媒体组发送失败 [%s] 第%d组 第%d次: %s，%.1fs后重试",
                                    group_name, bi + 1, attempt, e, wait)
                        await asyncio.sleep(wait)
                    else:
                        log.warning("Telegram 媒体组彻底失败 [%s] 第%d组（已重试%d次）: %s",
                                    group_name, bi + 1, MAX_RETRIES, e)
            if not sent:
                any_explicit_fail = True
            elif bi < len(batches) - 1:
                await asyncio.sleep(2.0)  # 组间间隔，避免 429

        total = len(images)
        result["images_ok"] = ok_count
        if any_explicit_fail and ok_count == 0:
            log.warning("  ✗ Telegram 推送失败 %d/%d 张 → [%s]", ok_count, total, group_name)
        else:
            result["main_ok"] = True

    body_zh = ""
    if result["main_ok"] and body_zh_future is not None:
        try:
            body_zh = body_zh_future.result()
        except Exception as e:
            log.warning("翻译 Future 异常 [%s]: %s", group_name, e)

    if result["main_ok"] and body_zh:
        if images:
            await asyncio.sleep(1.0)  # 图片组和翻译之间稍作停顿
        TELEGRAM_MAX = 4000
        body_fmt = _fmt_translation_tg(body_zh)
        if len(body_fmt) <= TELEGRAM_MAX:
            parts = [body_fmt]
        else:
            # 按双空行分段，保持中日对照的段落完整性
            paras = [p.strip() for p in body_fmt.split("\n\n") if p.strip()]
            parts = []
            buf = ""
            for p in paras:
                if len(p) > TELEGRAM_MAX:
                    if buf:
                        parts.append(buf.strip())
                        buf = ""
                    for i in range(0, len(p), TELEGRAM_MAX):
                        parts.append(p[i:i + TELEGRAM_MAX])
                elif buf and len(buf) + len(p) + 2 > TELEGRAM_MAX:
                    parts.append(buf.strip())
                    buf = p
                else:
                    buf = (buf + "\n\n" + p) if buf else p
            if buf:
                parts.append(buf.strip())

        ok = 0
        for idx, part in enumerate(parts):
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    await bot.send_message(chat_id=chat_id, text=part,
                                          parse_mode=ParseMode.HTML)
                    ok += 1
                    break
                except Exception as e:
                    if attempt < MAX_RETRIES:
                        wait = _retry_wait(e) or (2 ** attempt)
                        log.warning("Telegram 翻译发送失败 [%s] 第%d/%d段 第%d次: %s，%.1fs后重试",
                                    group_name, idx + 1, len(parts), attempt, e, wait)
                        await asyncio.sleep(wait)
                    else:
                        # HTML 模式下失败，回退到纯文本
                        try:
                            await bot.send_message(chat_id=chat_id, text=body_zh)
                            ok += 1
                            log.info("Telegram 翻译 [%s] 第%d段 HTML→纯文本回退成功",
                                     group_name, idx + 1)
                        except Exception as e2:
                            log.warning("Telegram 翻译发送彻底失败 [%s] 第%d/%d段: %s",
                                        group_name, idx + 1, len(parts), e2)
        result["tr_ok"] = (ok == len(parts))
        if ok > 0 and ok != len(parts):
            log.warning("  ⚠ 翻译部分成功 [%s]: %d/%d 段", group_name, ok, len(parts))

    return result


def push_to_group(group_key: str, group_name: str,
                  author: str, title: str, blog_url: str,
                  images: list[str], blog_date: str = "",
                  body_zh_future: Future | None = None) -> dict:
    """推送到对应坂道的 Telegram Bot，返回结果字典。"""
    skip_result = {
        "group": group_name,
        "main_ok": False,
        "images_ok": 0,
        "images_total": len(images),
        "batch_count": 0,
        "tr_ok": None,
        "skipped": True,
        "skip_reason": "",
    }

    if not TG_ENABLED:
        skip_result["skip_reason"] = "TG 总开关已关闭"
        return skip_result

    cfg = TG_GROUPS.get(group_key)
    if not cfg or not cfg.get("enabled"):
        skip_result["skip_reason"] = "未启用或未配置"
        return skip_result
    if not cfg.get("token") or not cfg.get("chat_id"):
        skip_result["skip_reason"] = "token/chat_id 未配置"
        return skip_result
    if author in get_blacklist(tg_group=group_key):
        skip_result["skip_reason"] = f"{author} 在黑名单中"
        return skip_result

    log.info("  ▶ Telegram 推送 [%s] ...", group_name)
    result = asyncio.run(_push_async(
        cfg["token"], cfg["chat_id"], group_name,
        author, title, blog_url, images, blog_date, body_zh_future
    ))
    result["group"] = group_name
    return result
