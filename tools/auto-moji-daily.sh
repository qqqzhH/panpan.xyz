#!/bin/bash
# 每日自动生成墨极日报并发布：拉新闻数据 → 生成当期 HTML + 更新 archive 数据 + 当日全录快照 → 有变化才 commit+push 主仓
# 由 Windows 任务计划 GenMojiDaily 每日 10:27 调起（新闻采集 9:00 + 同步之后）
set -u
SITE="C:/Users/MI/ZCodeProject/personal-site"
LOG="$SITE/tools/gen-moji-daily.log"
cd "$SITE" || exit 1
echo "[$(date '+%F %T')] gen start" >> "$LOG"
# 自愈防复发（9/07-9/25 事故：9/6 手工残渣 M moji_daily.html + 未跟踪副本让 pull 连败 19 天）：
# 生成物 moji_daily.html 每次运行都会整体重写，脏了直接复位；未跟踪的 moji_daily_YYYYMMDD.html 误命名副本清掉
# （只清 untracked——moji_daily_20260828.html 等旧命名体系文件是被跟踪的历史页面，不能动）。
git checkout -- moji_daily.html 2>/dev/null
git clean -f -q moji_daily_2026*.html 2>/dev/null
if ! git diff --quiet || [ -n "$(git status --porcelain)" ]; then
  echo "[$(date '+%F %T')] ABORT: worktree still dirty after self-heal (unexpected files), manual check needed" >> "$LOG"
  git status --porcelain >> "$LOG"
  exit 1
fi
git pull --rebase origin main >> "$LOG" 2>&1 || { echo "[$(date '+%F %T')] pull FAILED" >> "$LOG"; exit 1; }
python tools/gen-moji-daily.py >> "$LOG" 2>&1 || { echo "[$(date '+%F %T')] gen FAILED" >> "$LOG"; exit 1; }
# archive 温故知新页同步最近 7 天数据（ssh 拉最新 news.json）
ssh -o BatchMode=yes -o ConnectTimeout=20 root@47.96.236.50 'cat /opt/li-news/li-news-project/src/data/news.json' > "$SITE/tools/.news-tmp.json" 2>> "$LOG" \
  && python tools/gen-archive-data.py "$SITE/tools/.news-tmp.json" >> "$LOG" 2>&1 \
  || echo "[$(date '+%F %T')] archive update FAILED (keep old data)" >> "$LOG"
rm -f "$SITE/tools/.news-tmp.json"
# 当日全录快照（往期体系：墨极·YYYYMMDD.html）
[ -f moji_daily.html ] && cp moji_daily.html "墨极·$(date +%Y%m%d).html"
if git status --porcelain -- moji_daily.html archive.html "墨极·$(date +%Y%m%d).html" | grep -q .; then
  git add moji_daily.html archive.html "墨极·$(date +%Y%m%d).html"
  git commit -m "auto: 墨极日报每日更新 $(date '+%F')" >> "$LOG" 2>&1
  git push origin main >> "$LOG" 2>&1 || { echo "[$(date '+%F %T')] push FAILED" >> "$LOG"; exit 1; }
  echo "[$(date '+%F %T')] published -> CF Pages deploying" >> "$LOG"
else
  echo "[$(date '+%F %T')] no change, skip" >> "$LOG"
fi
