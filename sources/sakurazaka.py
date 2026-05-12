"""樱坂46 博客抓取（HTML 列表页 + 详情页解析）。"""
import re
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from network import get

log = logging.getLogger(__name__)

SAKURA_LIST_URL = "https://sakurazaka46.com/s/s46/diary/blog/list?ima=0000"


def _parse_date(raw: str) -> str:
    """统一樱坂各处日期格式到 'YYYY/MM/DD HH:MM' 或 'YYYY/MM/DD'。"""
    raw = raw.strip()
    m = re.match(r"(\d{4})(\d{2})(\d{2})\s+(\d{2})(\d{2})$", raw)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)} {m.group(4)}:{m.group(5)}"
    m2 = re.match(r"(\d{4})(\d{2})(\d{2})$", raw)
    if m2:
        return f"{m2.group(1)}/{m2.group(2)}/{m2.group(3)}"
    m3 = re.match(r"(\d{4})/(\d{1,2})/(\d{2})$", raw)
    if m3:
        return f"{m3.group(1)}/{int(m3.group(2)):02d}/{m3.group(3)}"
    return raw


def fetch_posts(limit: int = 30) -> list[dict]:
    try:
        r         = get(SAKURA_LIST_URL)
        soup      = BeautifulSoup(r.text, "html.parser")
        container = soup.find("ul", class_="com-blog-part")
        if not container:
            return []
        posts = []
        for item in container.find_all("li", class_="box", limit=limit):
            a_tag = item.find("a")
            if not a_tag:
                continue
            d_tag = item.find("p", class_="date")
            posts.append({
                "url":    urljoin("https://sakurazaka46.com", a_tag.get("href", "")),
                "title":  item.find("h3", class_="title").text.strip(),
                "author": item.find("p",  class_="name").text.strip(),
                "date":   d_tag.text.strip() if d_tag else "",
            })
        return posts
    except Exception as e:
        log.error("樱坂列表抓取失败: %s", e)
        return []


def fetch_images(url: str) -> list[str]:
    imgs, _ = fetch_detail(url)
    return imgs


def fetch_detail(url: str) -> tuple[list[str], str]:
    """返回 (图片列表, 精确发送时间)。"""
    try:
        r    = get(url)
        soup = BeautifulSoup(r.text, "html.parser")
        body = soup.find("div", class_="box-article") or soup
        imgs = [
            urljoin("https://sakurazaka46.com", img["src"])
            for img in body.find_all("img") if img.get("src")
        ]
        foot = soup.find("div", class_="blog-foot")
        date_str = ""
        if foot:
            d_tag = foot.find("p", class_="date")
            if d_tag:
                date_str = _parse_date(d_tag.text.strip())
        return imgs, date_str
    except Exception as e:
        log.warning("樱坂详情抓取失败 (%s): %s", url, e)
        return [], ""
