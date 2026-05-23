"""乃木坂46 博客抓取（JSONP API）。"""
import logging
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
            soup = BeautifulSoup(item.get("text", ""), "html.parser")
            images = [
                urljoin("https://www.nogizaka46.com", img["src"])
                for img in soup.find_all("img") if img.get("src")
            ]
            posts.append({
                "url":    url,
                "title":  item.get("title", "无标题"),
                "author": item.get("name",  "乃木坂46成员"),
                "images": images,
                "date":   item.get("date",  ""),
                "body":   soup.get_text("\n").strip(),
            })
        return posts
    except Exception as e:
        log.error("乃木坂列表抓取失败: %s", e)
        return []
