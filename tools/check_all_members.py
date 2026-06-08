"""遍历日向坂所有成员的博客列表页，统计5月21日后更新情况。"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
CUTOFF = datetime(2026, 5, 21, 0, 0, 0, tzinfo=JST)

session = requests.Session()
session.headers.update({
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36"
})

# 先获取主页，提取所有成员列表和 ct 值
print("=== 获取日向坂成员列表 ===")
r = session.get("https://www.hinatazaka46.com/s/official/diary/member?ima=0000")
soup = BeautifulSoup(r.text, "html.parser")

members = {}  # ct -> name
for a in soup.find_all("a", href=True):
    href = a["href"]
    if "/diary/member/list?ima=0000&ct=" in href:
        import re
        m = re.search(r'ct=(\d+)', href)
        if m:
            ct = m.group(1)
            name = a.text.strip()
            if name and ct != "000":  # skip "ポカ" (ct=000)
                members[ct] = name

print(f"找到 {len(members)} 个成员链接")
for ct, name in sorted(members.items()):
    print(f"  ct={ct}: {name}")

# 检查每个成员的最近博客
print(f"\n=== 检查每个成员5月21日后更新情况 ===")
posted_since = []
not_posted_since = []
no_posts = []

for ct, name in sorted(members.items(), key=lambda x: x[1]):
    url = f"https://www.hinatazaka46.com/s/official/diary/member/list?ima=0000&ct={ct}"
    try:
        r = session.get(url, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        items = soup.find_all("li", class_="p-blog-top__item")
        if not items:
            no_posts.append(name)
            print(f"  {name}: 无博客条目")
            continue

        # 获取最新一篇的时间
        latest_time = items[0].find("time", class_="c-blog-top__date")
        if not latest_time:
            no_posts.append(name)
            print(f"  {name}: 无法解析日期")
            continue

        date_str = latest_time.text.strip()
        dt = None
        for fmt in ("%Y.%m.%d %H:%M", "%Y.%m.%d"):
            try:
                dt = datetime.strptime(date_str, fmt).replace(tzinfo=JST)
                break
            except ValueError:
                continue

        if dt is None:
            print(f"  {name}: 日期解析失败 [{date_str}]")
            continue

        if dt >= CUTOFF:
            posted_since.append((name, dt, date_str))
            print(f"  {name}: 最新 {date_str} ✓")
        else:
            not_posted_since.append((name, dt, date_str))
            print(f"  {name}: 最新 {date_str} ✗ (5月21日前)")

    except Exception as e:
        print(f"  {name}: 抓取失败 ({e})")

print(f"\n{'='*60}")
print(f"日向坂46 统计结果:")
print(f"  5/21后更新过博客: {len(posted_since)}人")
for name, dt, ds in posted_since:
    print(f"    {name} ({ds})")
print(f"  5/21后未更新: {len(not_posted_since)}人")
for name, dt, ds in not_posted_since:
    print(f"    {name} (最新: {ds})")
if no_posts:
    print(f"  无博客数据: {len(no_posts)}人: {no_posts}")
