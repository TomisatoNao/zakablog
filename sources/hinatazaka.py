"""日向坂46 博客抓取（HTML 列表页解析）。"""
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from network import get

log = logging.getLogger(__name__)

HINATA_LIST_URL = "https://www.hinatazaka46.com/s/official/diary/member?ima=0000"


def fetch_posts(limit: int = 30) -> list[dict]:
    try:
        r    = get(HINATA_LIST_URL)
        soup = BeautifulSoup(r.text, "html.parser")
        posts = []
        for item in soup.find_all("li", class_="p-blog-top__item", limit=limit):
            a_tag = item.find("a")
            if not a_tag:
                continue
            t_tag = item.find("time", class_="c-blog-top__date")
            posts.append({
                "url":    urljoin("https://www.hinatazaka46.com", a_tag.get("href", "")),
                "title":  item.find("p",   class_="c-blog-top__title").text.strip(),
                "author": item.find("div", class_="c-blog-top__name").text.strip(),
                "date":   t_tag.text.strip() if t_tag else "",
            })
        return posts
    except Exception as e:
        log.error("日向坂列表抓取失败: %s", e)
        return []


def fetch_images(url: str) -> list[str]:
    try:
        r    = get(url)
        body = BeautifulSoup(r.text, "html.parser").find("div", class_="c-blog-article__text")
        if not body:
            return []
        return [
            ("https:" + img["src"] if img.get("src", "").startswith("//") else img["src"])
            for img in body.find_all("img")
            if "hinatazaka46.com" in img.get("src", "")
        ]
    except Exception as e:
        log.warning("日向坂图片抓取失败 (%s): %s", url, e)
        return []
