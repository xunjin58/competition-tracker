#!/usr/bin/env python3
"""
竞赛信息爬虫 - 从赛氪(saikr.com)搜索页抓取各赛事的截止时间、链接等。
每次运行会更新 data/scraped.json。
"""

import json
import time
import random
import re
import os
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).parent
COMPETITIONS_FILE = BASE_DIR / "data" / "competitions.json"
SCRAPED_FILE = BASE_DIR / "data" / "scraped.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://www.saikr.com/",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def search_saikr(name: str):
    """在赛氪搜索赛事，从搜索结果页直接提取第一个匹配结果的信息。"""
    search_url = "https://www.saikr.com/search"

    # 去掉中文引号
    clean_name = name.replace("\u201c", "").replace("\u201d", "").replace('"', "").replace("'", "")

    # 赛氪对长词不友好，依次尝试几个长度直到有结果
    n = len(clean_name)
    lengths = dict.fromkeys([n, 8, 6, 4, 3])  # 去重保序
    cards = []
    for length in lengths:
        if length > n:
            continue
        query = clean_name[:length]
        try:
            resp = SESSION.get(search_url, params={"search": query}, timeout=(8, 20))
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  [搜索失败] {name}: {e}")
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select("li.item.clearfix")
        if cards:
            break
        time.sleep(0.8)

    if not cards:
        print(f"  [未找到] {name}")
        return None

    # 选与原名最相似的卡片（最长公共子序列字符数）
    def similarity(card):
        card_text = card.get_text(separator="", strip=True)
        return sum(1 for ch in clean_name if ch in card_text)

    card = max(cards, key=similarity)
    result = {"source": "saikr"}

    # 提取链接
    link = card.select_one("a.link, a.linkcover")
    if link and link.get("href"):
        result["url"] = link["href"]
        if not result["url"].startswith("http"):
            result["url"] = "https://www.saikr.com" + result["url"]

    # 提取竞赛名（用于核验）
    title_tag = card.select_one("h3.tit a, a.link")
    if title_tag:
        result["title"] = title_tag.get_text(strip=True)

    # 提取各字段：遍历 p.event4-1-plan
    for p in card.select("p.event4-1-plan"):
        text = p.get_text(separator="", strip=True)
        if "报名时间" in text:
            # 格式：2026.01.20 ～ 2026.04.11 → 取截止日期（后半部分）
            m = re.search(r"[\d.]+\s*[～~]\s*([\d.]+)", text)
            if m:
                result["registration_deadline"] = m.group(1).strip()
        elif "比赛时间" in text:
            m = re.search(r"([\d.]+(?:\s*[～~]\s*[\d.]+)?)", text)
            if m:
                result["competition_time"] = m.group(1).strip()
        elif "竞赛级别" in text:
            result["level"] = text.replace("竞赛级别：", "").strip()
        elif "主办方" in text:
            result["organizer"] = text.replace("主办方：", "").strip()

    # 提取状态
    status_tag = card.select_one("em.event-status-tip")
    if status_tag:
        result["status"] = status_tag.get_text(strip=True)

    # 至少要有URL才算有效
    if "url" not in result:
        print(f"  [无链接] {name}")
        return None

    print(f"  [OK] {name} -> {result.get('url', '')} | 截止:{result.get('registration_deadline', '未知')}")
    return result


def load_existing() -> dict:
    if SCRAPED_FILE.exists():
        with open(SCRAPED_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"updated_at": "", "competitions": {}}


def save(data: dict):
    with open(SCRAPED_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    with open(COMPETITIONS_FILE, encoding="utf-8") as f:
        competitions = json.load(f)

    existing = load_existing()
    results = existing.get("competitions", {})

    print(f"共 {len(competitions)} 场赛事，开始爬取...")
    for comp in competitions:
        cid = str(comp["id"])
        name = comp["name"]

        # 跳过已有有效数据的（有URL才算有效）
        if cid in results and results[cid].get("url"):
            print(f"  [跳过] {name}（已有数据）")
            continue

        print(f"搜索: [{comp['level']}] {name}")
        info = search_saikr(name)
        results[cid] = info if info else {}

        # 礼貌性延迟
        time.sleep(random.uniform(1.5, 3.0))

    existing["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing["competitions"] = results
    save(existing)
    print(f"\n完成！数据已写入 {SCRAPED_FILE}")


if __name__ == "__main__":
    main()
