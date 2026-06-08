"""日向坂46 博客抓取（HTML 列表页解析）。"""
import re
import logging
from html import unescape
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from core.network import get

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


def _get_article(url: str) -> BeautifulSoup | None:
    r = get(url)
    return BeautifulSoup(r.text, "html.parser").find("div", class_="c-blog-article__text")


def fetch_images(url: str) -> list[str]:
    try:
        body = _get_article(url)
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


def fetch_body(url: str) -> str:
    """获取正文纯文本，用于翻译。保留 <br> 数量 + 图片占位符。"""
    try:
        body = _get_article(url)
        if not body:
            return ""
        html_str = str(body)
        # <img> → 【图片N】占位符（按出现顺序编号）
        _counter = [0]
        def _img_placeholder(m):
            _counter[0] += 1
            return f"\n【图片{_counter[0]}】\n"
        text = re.sub(r"<img[^>]*>", _img_placeholder, html_str, flags=re.IGNORECASE)
        # 每个 <br/> → 一个换行（保留原始数量）
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
        # 去掉其余 HTML 标签
        text = re.sub(r"<[^>]+>", "", text)
        # 解码 HTML 实体（&amp; → & 等）
        text = unescape(text)
        return text.strip()
    except Exception as e:
        log.warning("日向坂正文抓取失败 (%s): %s", url, e)
        return ""
