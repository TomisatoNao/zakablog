"""乃木坂46 博客抓取（JSONP API）。"""
import re
import logging
from html import unescape
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from core.network import get, parse_jsonp

log = logging.getLogger(__name__)

NOGI_API_URL = "https://www.nogizaka46.com/s/n46/api/list/blog"
NOGI_HEADERS = {"accept": "application/json", "x-requested-with": "XMLHttpRequest"}


def fetch_posts(limit: int = 30) -> list[dict]:
    try:
        r    = get(NOGI_API_URL, headers=NOGI_HEADERS)
        data = parse_jsonp(r.text)
        posts = []
        for item in data.get("data", [])[:limit]:
            code = item.get("code", "")
            url  = f"https://www.nogizaka46.com/s/n46/diary/detail/{code}?ima=0000&cd=MEMBER"
            raw_html = item.get("text", "")
            soup = BeautifulSoup(raw_html, "html.parser")
            images = [
                urljoin("https://www.nogizaka46.com", img["src"])
                for img in soup.find_all("img") if img.get("src")
            ]
            # <img> → 【图片N】占位符 + 保留 <br> 数量以还原网页分段
            _counter = [0]
            def _img_placeholder(m):
                _counter[0] += 1
                return f"\n【图片{_counter[0]}】\n"
            body_text = re.sub(r"<img[^>]*>", _img_placeholder, raw_html, flags=re.IGNORECASE)
            body_text = re.sub(r"<br\s*/?>", "\n", body_text, flags=re.IGNORECASE)
            body_text = re.sub(r"<[^>]+>", "", body_text)
            body_text = unescape(body_text).strip()
            posts.append({
                "url":    url,
                "title":  item.get("title", "无标题"),
                "author": item.get("name",  "乃木坂46成员"),
                "images": images,
                "date":   item.get("date",  ""),
                "body":   body_text,
            })
        return posts
    except Exception as e:
        log.error("乃木坂列表抓取失败: %s", e)
        return []
