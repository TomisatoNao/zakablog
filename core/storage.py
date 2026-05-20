"""状态持久化、图片下载与清理。"""
import os
import json
import shutil
import logging
from config import SAVE_DIR, RECORD_FILE, MAX_IMAGE_DIR_GB, MAX_IMAGE_MB
from core.network import get

log = logging.getLogger(__name__)


def _safe_filename(name: str, maxlen: int = 80) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in "._-")
    return safe[-maxlen:] if len(safe) > maxlen else safe


# ── 记录持久化 ──────────────────────────────
def load_records() -> dict:
    if os.path.exists(RECORD_FILE):
        try:
            with open(RECORD_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.warning("记录文件损坏，已重置: %s", e)
    return {"hinatazaka": "", "nogizaka": "", "sakurazaka": ""}


def save_records(records: dict) -> None:
    tmp = RECORD_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    os.replace(tmp, RECORD_FILE)


# ── 图片下载 ─────────────────────────────────
def download_images(group: str, author: str, title: str, img_urls: list[str]) -> None:
    safe_title = "".join(c for c in title if c.isalnum() or c in " !?円　").strip() or "无标题"
    target_dir = os.path.join(SAVE_DIR, f"{group}_{author}_{safe_title}")
    os.makedirs(target_dir, exist_ok=True)
    for i, url in enumerate(img_urls, 1):
        try:
            r = get(url, timeout=20)
            content_type = r.headers.get("Content-Type", "")
            if not content_type.startswith("image/"):
                log.warning("图片下载跳过 [%d/%d]：非图片 Content-Type=%s", i, len(img_urls), content_type)
                continue
            cl = int(r.headers.get("Content-Length", 0))
            if cl > MAX_IMAGE_MB * 1024 * 1024:
                log.warning("图片下载跳过 [%d/%d]：文件过大 %.1f MB", i, len(img_urls), cl / 1024 / 1024)
                continue
            filename = f"{i:02d}_{_safe_filename(url.split('/')[-1])}"
            with open(os.path.join(target_dir, filename), "wb") as f:
                f.write(r.content)
        except Exception as e:
            log.warning("图片下载失败 [%d/%d]: %s", i, len(img_urls), e)


# ── 容量管理 ─────────────────────────────────
def _get_dir_size_gb(path: str) -> float:
    total = 0
    if os.path.exists(path):
        for dirpath, _, filenames in os.walk(path):
            for fn in filenames:
                fp = os.path.join(dirpath, fn)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    return total / (1024 ** 3)


def check_and_cleanup() -> None:
    if MAX_IMAGE_DIR_GB <= 0:
        return
    size = _get_dir_size_gb(SAVE_DIR)
    if size > MAX_IMAGE_DIR_GB:
        log.info("图片目录已达 %.2f GB（上限 %d GB），清理中...", size, MAX_IMAGE_DIR_GB)
        try:
            shutil.rmtree(SAVE_DIR)
            log.info("图片目录已清理。")
        except Exception as e:
            log.error("清理图片目录失败: %s", e)
