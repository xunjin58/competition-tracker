#!/usr/bin/env python3
"""
竞赛信息爬虫 - 从赛氪(saikr.com)抓取各赛事的截止时间、答辩时间、参与条件等。
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
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def search_saikr(name: str) -> dict | None:
    """在赛氪搜索赛事，返回第一个匹配结果的详情。"""
    search_url = "https://www.saikr.com/vse/competition"
    params = {"kw": name}
    try:
        resp = SESSION.get(search_url, params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [搜索失败] {name}: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # 找赛事卡片列表
    cards = soup.select(".competition-item, .match-item, .vse-item, article.item")
    if not cards:
        # 备用：找所有含赛事链接的 a 标签
        cards = soup.select("a[href*='/vse/']")

    if not cards:
        print(f"  [未找到] {name}")
        return None

    # 取第一个结果
    first = cards[0]
    link_tag = first if first.name == "a" else first.find("a", href=True)
    if not link_tag:
        return None

    href = link_tag.get("href", "")
    if not href.startswith("http"):
        href = "https://www.saikr.com" + href

    return fetch_detail(href, name)


def fetch_detail(url: str, name: str) -> dict:
    """抓取赛事详情页，提取关键字段。"""
    try:
        resp = SESSION.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [详情页失败] {url}: {e}")
        return {"url": url, "source": "saikr"}

    soup = BeautifulSoup(resp.text, "html.parser")
    result = {"url": url, "source": "saikr"}

    # 提取页面中的日期信息
    # 赛氪详情页常见字段: 报名截止、作品提交、答辩/路演
    text = soup.get_text(separator="\n")

    def extract_date(pattern: str) -> str:
        m = re.search(pattern, text)
        return m.group(1).strip() if m else ""

    result["registration_deadline"] = extract_date(
        r"报名截止[时间：:]*\s*([0-9\-\/年月日 ]+)"
    ) or extract_date(r"截止[报名时间：:]*\s*([0-9\-\/年月日 ]+)")

    result["submission_deadline"] = extract_date(
        r"作品[提交收截止时间：:]*\s*([0-9\-\/年月日 ]+)"
    ) or extract_date(r"提交截止[：:]*\s*([0-9\-\/年月日 ]+)")

    result["defense_time"] = extract_date(
        r"(?:路演|答辩)[时间：:]*\s*([0-9\-\/年月日 ]+)"
    )

    # 参与条件
    cond_match = re.search(
        r"(?:参赛对象|参与条件|参赛资格|报名条件)[：:]\s*(.{10,200}?)(?:\n|。)",
        text,
    )
    result["requirements"] = cond_match.group(1).strip() if cond_match else ""

    # 奖励/奖金
    prize_match = re.search(
        r"(?:奖金|奖励|一等奖)[：:]\s*(.{5,100}?)(?:\n|。)",
        text,
    )
    result["prize"] = prize_match.group(1).strip() if prize_match else ""

    # 清理空字符串
    result = {k: v for k, v in result.items() if v != ""}

    print(f"  [OK] {name} -> {url}")
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

        # 跳过已有数据且数据较新的（可按需调整逻辑）
        if cid in results and results[cid].get("url"):
            print(f"  [跳过] {name}（已有数据）")
            continue

        print(f"搜索: [{comp['level']}] {name}")
        info = search_saikr(name)
        if info:
            results[cid] = info
        else:
            results[cid] = {}

        # 礼貌性延迟，避免被封
        time.sleep(random.uniform(2.0, 4.5))

    existing["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    existing["competitions"] = results
    save(existing)
    print(f"\n完成！数据已写入 {SCRAPED_FILE}")


if __name__ == "__main__":
    main()
