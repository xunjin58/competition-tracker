#!/bin/bash
# 每日本地运行公众号爬虫并推送到 GitHub
# 由 macOS launchd 每天自动调用

set -e

REPO_DIR="/Users/xunjin/Desktop/大学/比赛/赛事整合/competition-tracker"
LOG_FILE="$REPO_DIR/wechat_cron.log"

echo "=== $(date '+%Y-%m-%d %H:%M:%S') 开始运行 ===" >> "$LOG_FILE"

cd "$REPO_DIR"

# 拉取最新代码，避免冲突
git pull --rebase >> "$LOG_FILE" 2>&1

# 设置 Token 并运行爬虫
export RSS_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MTgiLCJ0eXBlIjoicnNzIn0.MYPM6N46M4XHRikcclmZ_eBVVGuIuyay_dB93_EC0nM"
python3 wechat_scraper.py >> "$LOG_FILE" 2>&1

# 如果数据有变化就 commit + push
git add data/wechat_news.json
if ! git diff --cached --quiet; then
    git commit -m "chore: 自动更新公众号竞赛文章 $(date +'%Y-%m-%d')"
    git push
    echo "已推送更新" >> "$LOG_FILE"
else
    echo "数据无变化，跳过推送" >> "$LOG_FILE"
fi

echo "=== 完成 ===" >> "$LOG_FILE"
