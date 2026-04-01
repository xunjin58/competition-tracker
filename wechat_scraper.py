#!/usr/bin/env python3
"""
公众号爬虫 - 从微信 RSS 抓取含竞赛关键词的文章，存入 data/wechat_news.json。
Token 从环境变量 RSS_TOKEN 读取。
"""

import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent
OUTPUT_FILE = BASE_DIR / "data" / "wechat_news.json"

RSS_URL = "https://wechatrss.waytomaster.com/api/rss/all"

# 竞赛相关关键词（标题命中任意一个即保留）
KEYWORDS = [
    "竞赛", "比赛", "大赛", "挑战杯", "创新创业",
    "获奖", "立项", "报名", "征集", "申报",
    "ACM", "蓝桥杯", "互联网+", "数学建模",
    "hackathon", "Hackathon", "编程", "开发大赛",
    "科技", "创作", "作品征", "奖学金", "表彰",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/rss+xml, application/xml",
}


def fetch_rss(token: str) -> list[dict]:
    resp = requests.get(RSS_URL, params={"token": token}, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date_str = (item.findtext("pubDate") or "").strip()
        try:
            pub_dt = parsedate_to_datetime(pub_date_str)
            pub_iso = pub_dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            pub_iso = ""
        items.append({"title": title, "link": link, "date": pub_iso})
    return items


def is_relevant(title: str) -> bool:
    return any(kw in title for kw in KEYWORDS)


def load_existing() -> list[dict]:
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            data = json.load(f)
            return data.get("articles", [])
    return []


def main():
    token = os.environ.get("RSS_TOKEN", "")
    if not token:
        print("错误：未设置 RSS_TOKEN 环境变量")
        return

    print("拉取 RSS...")
    items = fetch_rss(token)
    print(f"共 {len(items)} 篇文章，过滤关键词...")

    # 已有文章的链接集合（去重）
    existing = load_existing()
    existing_links = {a["link"] for a in existing}

    new_articles = []
    for item in items:
        if not is_relevant(item["title"]):
            continue
        if item["link"] in existing_links:
            print(f"  [已有] {item['title'][:40]}")
            continue
        print(f"  [新增] {item['title'][:60]}")
        new_articles.append(item)

    # 合并：新文章在前，按日期排序，最多保留200条
    all_articles = new_articles + existing
    all_articles.sort(key=lambda a: a.get("date", ""), reverse=True)
    all_articles = all_articles[:200]

    result = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "articles": all_articles,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n完成！新增 {len(new_articles)} 篇，共 {len(all_articles)} 篇。")


if __name__ == "__main__":
    main()
