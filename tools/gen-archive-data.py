#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把服务器 news.json 的最近 7 天数据写入 archive.html 的 var DATA / var TODAY。"""
import json, re, sys, os
from datetime import date, timedelta

SITE = r"C:\Users\MI\ZCodeProject\personal-site"
news_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ["TEMP"], "news.json")
target = date.today()
start = target - timedelta(days=6)

d = json.load(open(news_path, encoding="utf-8"))
items = [i for i in d["items"] if (i.get("publishedAt") or "")[:10] >= start.isoformat()]
items.sort(key=lambda i: (i.get("publishedAt") or ""), reverse=True)

def cn_time(iso):
    # "2026-09-06T08:00" -> "9月6日 08:00"
    m = re.match(r"\d{4}-(\d{1,2})-(\d{1,2})T(\d{2}):(\d{2})", iso or "")
    return f"{int(m.group(1))}月{int(m.group(2))}日 {m.group(3)}:{m.group(4)}" if m else ""

out = []
for n, i in enumerate(items, 1):
    pub = (i.get("publishedAt") or "").replace("T", " ")
    out.append({
        "id": i.get("id"), "day": (i.get("publishedAt") or "")[:10],
        "pub": pub, "time": cn_time(i.get("publishedAt")),
        "cat": i.get("category"), "imp": i.get("importance") or "normal",
        "url": i.get("sourceUrl"), "title": i.get("title"), "src": i.get("source"),
        "lede": i.get("summary"), "deep": i.get("deepDive") or "", "no": n,
    })

block = "var DATA = " + json.dumps(out, ensure_ascii=False, indent=1) + ";"
h = open(os.path.join(SITE, "archive.html"), encoding="utf-8").read()
h2, n1 = re.subn(r"var DATA = \[.*?\];", lambda m: block, h, count=1, flags=re.S)
h2, n2 = re.subn(r'var TODAY = "[0-9-]+";', f'var TODAY = "{target.isoformat()}";', h2, count=1)
assert n1 == 1 and n2 == 1, f"替换失败 DATA={n1} TODAY={n2}"
open(os.path.join(SITE, "archive.html"), "w", encoding="utf-8", newline="\n").write(h2)

# 自验
chk = open(os.path.join(SITE, "archive.html"), encoding="utf-8").read()
days = sorted(set(re.findall(r'"day": "(2026-\d\d-\d\d)"', chk)), reverse=True)
print(f"条数 {len(out)}（原 102）| 日期范围 {days[-1]} ~ {days[0]} | TODAY 已更新: {target.isoformat() in chk}")
print("div配平:", chk.count("<div") == chk.count("</div>"), "| script配平:", chk.count("<script") == chk.count("</script>"))
