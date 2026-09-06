#!/bin/bash
# 每日自动生成墨极日报并发布：拉新闻数据 → 生成当期 HTML → 有变化才 commit+push 主仓
# 由 Windows 任务计划 GenMojiDaily 每日 10:27 调起（新闻采集 9:00 + 同步之后）
set -u
SITE="C:/Users/MI/ZCodeProject/personal-site"
LOG="$SITE/tools/gen-moji-daily.log"
cd "$SITE" || exit 1
echo "[$(date '+%F %T')] gen start" >> "$LOG"
git pull --rebase origin main >> "$LOG" 2>&1 || { echo "[$(date '+%F %T')] pull FAILED" >> "$LOG"; exit 1; }
python tools/gen-moji-daily.py >> "$LOG" 2>&1 || { echo "[$(date '+%F %T')] gen FAILED" >> "$LOG"; exit 1; }
# archive 温故知新页同步最近 7 天数据（ssh 拉最新 news.json）
ssh -o BatchMode=yes -o ConnectTimeout=20 root@47.96.236.50 'cat /opt/li-news/li-news-project/src/data/news.json' > "$SITE/../.moji-news-tmp.json" 2>> "$LOG" \
  && python tools/gen-archive-data.py "$SITE/../.moji-news-tmp.json" >> "$LOG" 2>&1 \
  || echo "[$(date '+%F %T')] archive update FAILED (keep old data)" >> "$LOG"
rm -f "$SITE/../.moji-news-tmp.json"
# archive 温故知新页同步最近 7 天数据（ssh 拉最新 news.json）
ssh -o BatchMode=yes -o ConnectTimeout=20 root@47.96.236.50 'cat /opt/li-news/li-news-project/src/data/news.json' > "$SITE/tools/.news-tmp.json" 2>> "$LOG" \
  && python tools/gen-archive-data.py "$SITE/tools/.news-tmp.json" >> "$LOG" 2>&1 \
  || echo "[$(date '+%F %T')] archive update FAILED (keep old data)" >> "$LOG"
rm -f "$SITE/tools/.news-tmp.json"
if git status --porcelain -- moji_daily.html archive.html | grep -q .; then
  git add moji_daily.html archive.html
  git commit -m "auto: 墨极日报每日更新 $(date '+%F')" >> "$LOG" 2>&1
  git push origin main >> "$LOG" 2>&1 || { echo "[$(date '+%F %T')] push FAILED" >> "$LOG"; exit 1; }
  echo "[$(date '+%F %T')] published -> CF Pages deploying" >> "$LOG"
else
  echo "[$(date '+%F %T')] no change, skip" >> "$LOG"
fi
