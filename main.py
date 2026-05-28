"""主调度：面板渲染、巡检编排、主循环。"""
import sys
import time
import random
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from config import (
    RESET, BOLD, DIM, C_TIME, C_INFO, C_WARN, C_ERR, C_NEW, C_SLEEP,
    USE_COLOR, BOTS, BLACKLIST, get_blacklist, QQ_ENABLED, TG_ENABLED, TG_GROUPS,
    TRANSLATE_ENABLED, GEMINI_API_KEY, GEMINI_MODELS,
    DAY_MIN, DAY_MAX, NIGHT_MIN, NIGHT_MAX, JST,
)
from sources import hinatazaka, nogizaka, sakurazaka
from core.storage import load_records, save_records, download_images, check_and_cleanup
from core.translator import translate
from bots.qq_bot import push_to_all
from bots import tg_bot

log = logging.getLogger(__name__)

TASKS = [
    ("日向坂46", hinatazaka.fetch_posts, hinatazaka.fetch_images, "hinatazaka",  False),
    ("乃木坂46", nogizaka.fetch_posts,   None,                    "nogizaka",    False),
    ("樱坂46",   sakurazaka.fetch_posts, sakurazaka.fetch_images, "sakurazaka",  True),
]

_latest: dict[str, tuple[str, str]] = {
    "日向坂46": ("", ""),
    "乃木坂46": ("", ""),
    "樱坂46":   ("", ""),
}


# ── 工具 ─────────────────────────────────────
def _fmt_time(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}分{s:02d}秒" if m else f"{s}秒"


def _is_night_jst() -> bool:
    return 0 <= datetime.now(JST).hour < 8


def _next_interval() -> tuple[int, bool]:
    night = _is_night_jst()
    return (random.randint(NIGHT_MIN, NIGHT_MAX), True) if night \
           else (random.randint(DAY_MIN, DAY_MAX), False)


def _clear_terminal():
    if USE_COLOR:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()



# ── 面板 ─────────────────────────────────────
def _render_panel(cycle: int, interval: int, is_night: bool,
                  status_lines: list[str]) -> None:
    _clear_terminal()
    W = 54
    now  = time.strftime("%Y-%m-%d %H:%M:%S")
    mode = f"{C_SLEEP}🌙 夜间{RESET}" if is_night else f"{C_INFO}☀️  日间{RESET}"

    print(f"{BOLD}{'═' * W}{RESET}")
    print(f"{BOLD}   🌸 坂道联合博客监控中心{RESET}")
    print(f"   日向坂46 / 乃木坂46 / 樱坂46")
    print(f"{DIM}{'-' * W}{RESET}")
    print(f"   状态   {C_INFO}● 运行中{RESET}   第 {BOLD}{cycle}{RESET} 轮   {mode}模式")
    print(f"   时间   {C_TIME}{now}{RESET}")
    print(f"{DIM}{'-' * W}{RESET}")

    print(f"   {BOLD}本轮巡检{RESET}")
    for s in status_lines:
        print(f"   {s}")
    print(f"{DIM}{'-' * W}{RESET}")

    print(f"   {BOLD}最新博客{RESET}")
    labels = {"日向坂46": "☀️ 日向", "乃木坂46": "💜 乃木", "樱坂46": "🌸 樱坂"}
    for group, (author, title) in _latest.items():
        label = labels.get(group, group)
        if author:
            t_disp = title[:16] + ("…" if len(title) > 16 else "")
            print(f"   {label}  {C_NEW}{author}{RESET}  {DIM}《{t_disp}》{RESET}")
        else:
            print(f"   {label}  {DIM}暂无数据{RESET}")
    print(f"{DIM}{'-' * W}{RESET}")

    print(f"   {BOLD}推送配置{RESET}")
    # QQ
    if not QQ_ENABLED:
        print(f"   QQ  {DIM}✗ 总开关已关闭{RESET}")
    elif not BOTS:
        print(f"   QQ  {DIM}未配置 Bot{RESET}")
    else:
        for bot in BOTS:
            parts = []
            for k, abbr in [("hinatazaka", "日向"), ("nogizaka", "乃木"), ("sakurazaka", "樱坂")]:
                en = bot["groups"].get(k, True)
                parts.append(f"{abbr}{C_INFO}✓{RESET}" if en else f"{abbr}{DIM}✗{RESET}")
            print(f"   QQ  [{bot['name']}]  {'  '.join(parts)}")
    # Telegram
    if not TG_ENABLED:
        print(f"   TG  {DIM}✗ 总开关已关闭{RESET}")
    else:
        tg_parts = []
        for k, abbr in [("hinatazaka", "日向"), ("nogizaka", "乃木"), ("sakurazaka", "樱坂")]:
            cfg = TG_GROUPS.get(k, {})
            if cfg.get("enabled") and cfg.get("token") and cfg.get("chat_id"):
                tg_parts.append(f"{abbr}{C_INFO}✓{RESET}")
            else:
                tg_parts.append(f"{abbr}{DIM}✗{RESET}")
        print(f"   TG  {'  '.join(tg_parts)}")

    moon = "🌙" if is_night else "💤"
    print(f"   {DIM}{moon} 下次巡检：{_fmt_time(interval)} 后（Ctrl+C 退出）{RESET}")
    print(f"{BOLD}{'═' * W}{RESET}")


# ── 巡检 ─────────────────────────────────────
def run_monitor(cycle: int, interval: int = 0, is_night: bool = False) -> None:
    records = load_records()
    status  = []

    for group_name, fetch_list, fetch_images, key, need_detail in TASKS:
        try:
            posts = fetch_list()
        except Exception as e:
            log.error("[%s] 抓取异常: %s", group_name, e)
            status.append(f"[{group_name}] {C_ERR}抓取失败{RESET}")
            continue

        if not posts:
            status.append(f"[{group_name}] {DIM}暂无数据{RESET}")
            continue

        _latest[group_name] = (posts[0]["author"], posts[0]["title"])

        last_url = records.get(key, "")
        unseen   = []
        for post in posts:
            if post["url"] == last_url:
                break
            unseen.append(post)

        if not unseen:
            status.append(f"[{group_name}] {C_INFO}✓ 无更新{RESET}")
            continue

        if last_url and len(unseen) == len(posts):
            log.warning("[%s] 记录 URL 已移出扫描范围，跳过推送直接推进: %s", group_name, last_url)
            records[key] = posts[0]["url"]
            save_records(records)
            status.append(f"[{group_name}] {C_WARN}⚠ 离线过久，直接推进{RESET}")
            continue

        if not last_url:
            status.append(f"[{group_name}] {DIM}首次记录{RESET}")
            records[key] = posts[0]["url"]
            save_records(records)
            continue

        for post in reversed(unseen):
            url, title, author = post["url"], post["title"], post["author"]

            if author in get_blacklist():
                status.append(f"[{group_name}] {DIM}🚫 {author}（全局黑名单）{RESET}")
                records[key] = url
                save_records(records)
                continue

            blog_date = post.get("date", "")
            status.append(f"[{group_name}] {C_NEW}📢 {author}《{title[:12]}{'…' if len(title)>12 else ''}》{RESET}")
            log.info("📢 新博客 | [%s] %s | 《%s》| %s | %s",
                     group_name, author, title, blog_date, url)

            images: list[str] = post.get("images", [])
            body = ""
            if fetch_images and not images:
                if need_detail:
                    images, detail_date, body = sakurazaka.fetch_detail(url)
                    if detail_date:
                        blog_date = detail_date
                else:
                    images = fetch_images(url)
                    body = hinatazaka.fetch_body(url)
            elif not need_detail:
                body = post.get("body", "")

            # 全部任务同时启动：下载 + 翻译 + QQ 推送 + TG 推送
            tr_future = None
            max_workers = (1 if images else 0) + len(BOTS) + 1  # dl + QQ bots + TG
            if TRANSLATE_ENABLED and body:
                max_workers += 1  # translate

            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures: dict[str, object] = {}

                if images:
                    futures["dl"] = pool.submit(download_images, group_name, author, title, images)

                if TRANSLATE_ENABLED and body:
                    log.info("  🌐 翻译中...")
                    tr_future = pool.submit(translate, body)

                futures["qq"] = pool.submit(push_to_all, key, group_name, author, title, url,
                                            images, blog_date, tr_future)
                futures["tg"] = pool.submit(tg_bot.push_to_group, key, group_name, author, title, url,
                                            images, blog_date, tr_future)

                pushed_qq = False
                pushed_tg = False
                for name, f in futures.items():
                    try:
                        result = f.result()
                        if name == "qq":
                            pushed_qq = result
                        elif name == "tg":
                            pushed_tg = result
                    except Exception as e:
                        log.warning("并行任务异常 [%s]: %s", name, e)

                if tr_future is not None:
                    try:
                        body_zh = tr_future.result()
                        if body_zh:
                            log.info("  ✓ 翻译完成 (%d 字)", len(body_zh))
                    except Exception:
                        pass

            if pushed_qq or pushed_tg:
                records[key] = url
                save_records(records)
                if not pushed_qq:
                    log.warning("  ⚠ QQ 推送失败 [%s]，仅 Telegram 成功", group_name)
                if not pushed_tg:
                    log.warning("  ⚠ Telegram 推送失败 [%s]，仅 QQ 成功", group_name)
            else:
                log.warning("  ⚠ 推送全部失败 [%s]，状态未推进，下轮重试", group_name)

    _render_panel(cycle, interval, is_night, status)
    check_and_cleanup()


# ── 入口 ─────────────────────────────────────
def main() -> None:
    _clear_terminal()
    if not BOTS:
        log.warning("未配置任何 Bot（请设置 BOT1_CLIENT_SECRET 等环境变量），仅做本地监控。")
    log.info("监控服务已启动  日间:%d~%ds  夜间:%d~%ds",
             DAY_MIN, DAY_MAX, NIGHT_MIN, NIGHT_MAX)
    # Gemini 翻译状态
    if not TRANSLATE_ENABLED:
        log.info("Gemini 翻译: ✗ 总开关已关闭")
    elif not GEMINI_API_KEY:
        log.warning("Gemini 翻译: ✗ API Key 未配置，翻译不可用")
    elif not GEMINI_MODELS:
        log.warning("Gemini 翻译: ✗ 模型池为空，翻译不可用")
    else:
        model_names = [m["name"] for m in GEMINI_MODELS]
        log.info("Gemini 翻译: ✓ 已启用 | API Key: 已配置 | 模型池: %s", ", ".join(model_names))
    # 黑名单摘要
    parts = [f"global={len(BLACKLIST.get('global', set()))}"]
    for i in range(1, 5):
        name = f"Bot {i}"
        bl = BLACKLIST.get(name, set())
        parts.append(f"{name}={len(bl)}" if bl else f"{name}=(空)")
    tg_count = sum(len(BLACKLIST.get(f"tg.{k}", set())) for k in ("hinatazaka", "nogizaka", "sakurazaka"))
    parts.append(f"TG={tg_count}" if tg_count else "TG=(空)")
    log.info("黑名单: %s", " | ".join(parts))
    for key, label in [("global", None), ("Bot 1", None), ("Bot 2", None), ("Bot 3", None), ("Bot 4", None),
                       ("tg.hinatazaka", "TG日向"), ("tg.nogizaka", "TG乃木"), ("tg.sakurazaka", "TG樱")]:
        names = BLACKLIST.get(key, set())
        if names:
            tag = label or key
            log.info("  [%s] %s", tag, ", ".join(sorted(names)))

    cycle = 1
    run_monitor(cycle)

    while True:
        try:
            interval, is_night = _next_interval()
            next_time = time.time() + interval
            moon = "🌙" if is_night else "💤"

            while True:
                remaining = int(next_time - time.time())
                if remaining <= 0:
                    break
                if USE_COLOR:
                    sys.stdout.write(
                        "\033[2A\033[2K\033[G"
                        f"   {DIM}{moon} 下次巡检：{_fmt_time(remaining)} 后（Ctrl+C 退出）{RESET}\n"
                        f"{BOLD}{'═' * 54}{RESET}\n"
                    )
                    sys.stdout.flush()
                time.sleep(min(10, remaining))

            cycle += 1
            run_monitor(cycle, interval, is_night)

        except KeyboardInterrupt:
            _clear_terminal()
            print(f"\n{C_INFO}👋 监控已停止，再见！{RESET}\n")
            sys.exit(0)
        except Exception as e:
            log.error("监控轮次异常（将继续运行）: %s", e)
