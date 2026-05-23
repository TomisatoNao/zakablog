"""Telegram Bot：文本/媒体组推送，一个坂道一个机器人。"""
import asyncio
import logging
from config import TG_ENABLED, TG_GROUPS, get_blacklist, MAX_RETRIES

log = logging.getLogger(__name__)


def _chunks(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


async def _push_async(token: str, chat_id: str, group_name: str,
                      author: str, title: str, blog_url: str,
                      images: list[str], blog_date: str = "") -> bool:
    try:
        from telegram import Bot, InputMediaPhoto
        from telegram.constants import ParseMode
        from telegram.error import TimedOut
    except ImportError:
        log.warning("python-telegram-bot 未安装，跳过 Telegram 推送")
        return False

    bot = Bot(token=token, read_timeout=120, connect_timeout=10, write_timeout=60)
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

    # 无图片：纯文字
    if not images:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                await bot.send_message(chat_id=chat_id, text=html_text,
                                       parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                log.info("  ✓ Telegram 推送 → [%s]", group_name)
                return True
            except TimedOut:
                log.warning("Telegram 推送超时 [%s]（服务端可能已收到），视为成功", group_name)
                return True
            except Exception as e:
                if attempt < MAX_RETRIES:
                    wait = 2 ** attempt
                    log.warning("Telegram 推送失败 [%s] 第%d次: %s，%ds后重试",
                                group_name, attempt, e, wait)
                    await asyncio.sleep(wait)
                else:
                    log.warning("  ✗ Telegram 推送失败 [%s]（已重试%d次）: %s",
                                group_name, MAX_RETRIES, e)
                    return False
        return False

    # 有图片：第一张带 HTML 摘要，≤10 张/组
    batches = list(_chunks(images, 10))
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
                    wait = 2 ** attempt
                    log.warning("Telegram 媒体组发送失败 [%s] 第%d组 第%d次: %s，%ds后重试",
                                group_name, bi + 1, attempt, e, wait)
                    await asyncio.sleep(wait)
                else:
                    log.warning("Telegram 媒体组彻底失败 [%s] 第%d组（已重试%d次）: %s",
                                group_name, bi + 1, MAX_RETRIES, e)
        if not sent:
            any_explicit_fail = True

    total = len(images)
    if any_explicit_fail and ok_count == 0:
        log.warning("  ✗ Telegram 推送失败 %d/%d 张 → [%s]", ok_count, total, group_name)
        return False
    if total > 10:
        log.info("  ✓ Telegram 推送 %d/%d 张（%d 组）→ [%s]",
                 ok_count, total, len(batches), group_name)
    else:
        log.info("  ✓ Telegram 推送 %d/%d 张 → [%s]", ok_count, total, group_name)
    return True


def push_to_group(group_key: str, group_name: str,
                  author: str, title: str, blog_url: str,
                  images: list[str], blog_date: str = "") -> bool:
    """推送到对应坂道的 Telegram Bot，返回文字通知是否成功。"""
    if not TG_ENABLED:
        log.debug("Telegram 总开关已关闭")
        return False

    cfg = TG_GROUPS.get(group_key)
    if not cfg or not cfg.get("enabled"):
        log.debug("Telegram [%s] 未启用或未配置", group_name)
        return False
    if not cfg.get("token") or not cfg.get("chat_id"):
        log.debug("Telegram [%s] token/chat_id 未配置，跳过", group_name)
        return False
    if author in get_blacklist(tg_group=group_key):
        log.info("  🚫 Telegram [%s] %s 在黑名单中，跳过", group_name, author)
        return False

    log.info("  ▶ Telegram 推送 [%s] ...", group_name)
    return asyncio.run(_push_async(
        cfg["token"], cfg["chat_id"], group_name,
        author, title, blog_url, images, blog_date
    ))
