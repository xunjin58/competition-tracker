#!/usr/bin/env python3
"""
公众号爬虫 - 从微信 RSS 抓取含竞赛关键词的文章，提取结构化信息，存入 data/wechat_news.json。
Token 从环境变量 RSS_TOKEN 读取。
"""

import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent
OUTPUT_FILE = BASE_DIR / "data" / "wechat_news.json"
RSS_URL = "https://wechatrss.waytomaster.com/api/rss/all"

KEYWORDS = [
    "竞赛", "比赛", "大赛", "挑战杯", "创新创业",
    "获奖", "立项", "报名", "征集", "申报",
    "ACM", "蓝桥杯", "互联网+", "数学建模",
    "hackathon", "Hackathon", "编程", "开发大赛",
    "科技", "作品征", "表彰", "奖学金",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://wechatrss.waytomaster.com/",
    "Connection": "keep-alive",
}


# ── HTML → 纯文本 ──────────────────────────────────────────────
class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lines = []
    def handle_data(self, data):
        s = data.strip()
        if s:
            self.lines.append(s)

def html_to_text(html: str) -> str:
    p = TextExtractor()
    p.feed(html)
    return "\n".join(p.lines)


# ── 日期规范化：把各种中文日期格式转成 YYYY-MM-DD ───────────────
def normalize_date(raw: str) -> str:
    raw = raw.strip()
    # 2026年4月3日 / 2026.04.03 / 2026-04-03
    m = re.search(r"(\d{4})[年.\-/](\d{1,2})[月.\-/](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    # 4月3日（无年份，补当前年）
    m = re.search(r"(\d{1,2})月(\d{1,2})日", raw)
    if m:
        year = datetime.now().year
        return f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return ""


# ── 从正文文本中提取关键字段 ──────────────────────────────────
def extract_fields(text: str) -> dict:
    result = {}

    # 截止日期：优先找"截止时间"，其次"报名截止"，再找"报名时间"区间的结束日期
    patterns_deadline = [
        r"截止时间[^\d]*?((?:\d{4}[年.\-/])?\d{1,2}月\d{1,2}日[^\n，,。；]*)",
        r"报名截止[^\d]*?((?:\d{4}[年.\-/])?\d{1,2}月\d{1,2}日[^\n，,。；]*)",
        r"(?:报名时间|报名日期)[^\n]*?至\s*((?:\d{4}[年.\-/])?\d{1,2}月\d{1,2}日[^\n，,。；]*)",
        r"(?:报名时间|报名日期)[^\n]*?[～~]\s*((?:\d{4}[年.\-/])?\d{1,2}月\d{1,2}日[^\n，,。；]*)",
    ]
    for pat in patterns_deadline:
        m = re.search(pat, text)
        if m:
            d = normalize_date(m.group(1))
            if d:
                result["deadline"] = d
                break

    # 比赛/活动时间
    m = re.search(
        r"(?:比赛时间|活动时间|大赛时间)[^\d\n]*?((?:\d{4}[年.\-/])?\d{1,2}月\d{1,2}日[^\n]{0,30})",
        text,
    )
    if m:
        result["competition_time"] = m.group(1).strip()

    # 参赛对象
    m = re.search(
        r"(?:参赛对象|参与对象|报名对象|参赛资格|适合对象)[：:]\s*([^\n]{5,80})",
        text,
    )
    if m:
        result["requirements"] = m.group(1).strip()

    # 报名材料
    m = re.search(
        r"(?:报名材料|参赛材料|提交材料|所需材料)[^\n]*?\n([^\n]{5,200})",
        text,
    )
    if m:
        result["materials"] = m.group(1).strip()

    # 联系邮箱
    m = re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
    if m:
        result["contact_email"] = m.group(0)

    return result


# ── 主流程 ────────────────────────────────────────────────────
def fetch_rss(token: str) -> list[dict]:
    resp = requests.get(RSS_URL, params={"token": token}, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link  = (item.findtext("link") or "").strip()
        desc  = (item.findtext("description") or "")
        pub   = (item.findtext("pubDate") or "").strip()
        try:
            pub_iso = parsedate_to_datetime(pub).astimezone(timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            pub_iso = ""
        items.append({"title": title, "link": link, "description": desc, "date": pub_iso})
    return items


def is_relevant(title: str) -> bool:
    return any(kw in title for kw in KEYWORDS)


def load_existing() -> list[dict]:
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            return json.load(f).get("articles", [])
    return []


def main():
    token = os.environ.get("RSS_TOKEN", "")
    if not token:
        print("错误：未设置 RSS_TOKEN 环境变量")
        return

    print("拉取 RSS...")
    items = fetch_rss(token)
    print(f"共 {len(items)} 篇文章，过滤关键词...")

    existing = load_existing()
    existing_links = {a["link"] for a in existing}

    new_articles = []
    for item in items:
        if not is_relevant(item["title"]):
            continue
        if item["link"] in existing_links:
            print(f"  [已有] {item['title'][:40]}")
            continue

        text = html_to_text(item["description"])
        fields = extract_fields(text)

        # 去掉账号前缀 [xxx]
        clean_title = re.sub(r"^\[.*?\]\s*", "", item["title"])

        article = {
            "title": clean_title,
            "link":  item["link"],
            "date":  item["date"],
            **fields,
        }
        print(f"  [新增] {clean_title[:50]} | 截止:{fields.get('deadline','?')}")
        new_articles.append(article)

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
