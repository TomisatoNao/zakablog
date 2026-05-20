# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
python blog.py                    # 启动监控（入口）
pip install -r requirements.txt   # 安装依赖
pip install httpx websockets      # 额外依赖：获取 QQ openid 工具需要
python tools/get_qq_openid.py     # 获取 QQ Bot 目标 openid
python -m py_compile main.py      # 快速语法检查（无测试套件）
```

## Architecture

Single-process polling monitor with ANSI terminal panel. The main loop (`main.py`) iterates over three blog sources on a randomized interval (short by day, long by night JST), compares post lists against a URL-based watermark in `data/blog_records.json`, and pushes new posts to QQ Bot + Telegram Bot.

### Data flow

1. **Fetch**: `sources/*.py` — each module scrapes its official blog site and returns `list[dict]` with keys `url, title, author, date[, images]`. Posts are ordered newest-first.
2. **Diff**: `main.py` compares the fetched list against `records[key]` (the last successfully pushed URL). New posts = everything before that URL.
3. **Download**: `core/storage.py` — `download_images()` saves images to `blog_images/{group}_{author}_{title}/`.
4. **Push**: `bots/qq_bot.py` sends markdown text then images; `bots/tg_bot.py` sends HTML text then media groups. Each runs independently; the record advances if at least one platform succeeds.
5. **Advance**: `records[key]` is updated to the newest pushed URL and atomically written (write-tmp-then-replace).

### Key design decisions

- **config.py has import side effects**: it initializes the logging system (console + rotating file) at module level. All other modules `import logging; log = logging.getLogger(__name__)` and expect this setup.
- **Three scraping strategies**: Hinatazaka parses HTML list, Nogizaka uses JSONP API (images embedded in list response), Sakurazaka parses HTML list then fetches a detail page for images + precise date. This is configured via `TASKS` tuple in `main.py` — the 5th field `need_detail` controls whether `fetch_detail()` is called.
- **`network.post()` returns `{"err_code": -1}` on failure** — callers check `resp.get("err_code", 0) == 0` for success, not truthiness.
- **`network.get()` raises on failure** after exhausting retries with exponential backoff (429/502/503/504 are retryable). Callers catch and return `[]`.
- **JST timezone** is used for night-mode detection (0:00–8:00 JST) and log timestamps, independent of server timezone.
- **Colored output** uses ANSI escape codes gated by `sys.stdout.isatty()` so piping/redirection works cleanly.
- **Blacklist** is a JSON array of author name strings in `data/blacklist.json`. Blacklisted authors are skipped silently (record advances without push).
- **Image directory cleanup** is all-or-nothing: if `blog_images/` exceeds `MAX_IMAGE_DIR_GB`, the entire directory is deleted.

### Bot push edge cases

- `_send_text()` falls back from markdown (`msg_type: 2`) to plain text (`msg_type: 0`) if the first POST fails with non-zero err_code.
- Multi-bot push has a `BOT_SWITCH_DELAY` (3s) between bots to avoid rate limiting.
- Records only advance if `pushed_qq or pushed_tg` is True — if both platforms fail, the URL is retried next cycle.
