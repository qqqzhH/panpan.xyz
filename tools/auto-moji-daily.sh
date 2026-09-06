#!/bin/bash
# 每日自动生成墨极日报并发布：拉新闻数据 → 生成当期 HTML → 有变化才 commit+push 主仓
# 由 Windows 任务计划 GenMojiDaily 每日 10:27 调起（新闻采集 9:00 + 同步之后）
set -u
SITE="C:/Users/MI/ZCodeProject/personal-site"
LOG="C:/Users/MI/ZCodeProject/personal-site/tools/gen-moji-daily.log"
cd "$SITE" || exit 1
echo "[$(date '+%F %T')] gen start" >> "$LOG"
git pull --rebase origin main >> "$LOG" 2>&1 || { echo "[$(date '+%F %T')] pull FAILED" >> "$LOG"; exit 1; }
python tools/gen-moji-daily.py >> "$LOG" 2>&1 || { echo "[$(date '+%F %T')] gen FAILED" >> "$LOG"; exit 1; }
if git status --porcelain -- moji_daily.html | grep -q .; then
  git add moji_daily.html
  git commit -m "auto: 墨极日报每日更新 $(date '+%F')" >> "$LOG" 2>&1
  git push origin main >> "$LOG" 2>&1 || { echo "[$(date '+%F %T')] push FAILED" >> "$LOG"; exit 1; }
  echo "[$(date '+%F %T')] published -> CF Pages deploying" >> "$LOG"
else
  echo "[$(date '+%F %T')] no change, skip" >> "$LOG"
fi
