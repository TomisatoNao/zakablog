"""Telegram Bot：文本/媒体组推送，一个坂道一个机器人。"""
import asyncio
import logging
from config import TG_ENABLED, TG_GROUPS

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
    except ImportError:
        log.warning("python-telegram-bot 未安装，跳过 Telegram 推送")
        return False

    bot = Bot(token=token)
    emoji = "🌸" if "樱" in group_name else "☀️" if "日" in group_name else "💜" if "乃" in group_name else "🤖"

    date_line = f"<b>时间</b>：{blog_date}\n" if blog_date else ""
    html_text = (
        f"{emoji} <b>{group_name} 博客更新</b>\n\n"
        f"<b>作者</b>：{author}\n"
        f"<b>标题</b>：{title}\n"
        f"{date_line}"
        f"<b>照片</b>：共 {len(images)} 张\n\n"
        f"👉 <a href=\"{blog_url}\">博客链接</a>"
    )

    try:
        await bot.send_message(chat_id=chat_id, text=html_text,
                               parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        log.info("  ✓ Telegram 文字通知 → [%s]", group_name)
    except Exception as e:
        log.warning("  ✗ Telegram 文字通知失败 [%s]: %s", group_name, e)
        return False

    # 媒体组发送（≤10 张/组）
    ok_count = 0
    for batch in _chunks(images, 10):
        try:
            media = [InputMediaPhoto(media=url) for url in batch]
            await bot.send_media_group(chat_id=chat_id, media=media)
            ok_count += len(batch)
        except Exception as e:
            log.warning("Telegram 媒体组发送失败 [%s] %d 张: %s",
                        group_name, len(batch), e)
    if images:
        log.info("  📷 Telegram 图片 %d/%d → [%s]", ok_count, len(images), group_name)
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

    log.info("  ▶ Telegram 推送 [%s] ...", group_name)
    return asyncio.run(_push_async(
        cfg["token"], cfg["chat_id"], group_name,
        author, title, blog_url, images, blog_date
    ))
