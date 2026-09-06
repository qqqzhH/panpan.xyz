#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen-moji-daily.py —— 「墨极日报」生成器（攀攀.xyz /moji_daily）

把 li-news 生产库 news.json 里目标日期的新闻，渲染成墨极日报版式（骨架与样式
完整复刻 2026-08-28 第 240 期原版），覆盖写 site 目录下 moji_daily.html。

用法：
    python tools/gen-moji-daily.py                      # 目标日期=今天，ssh 拉取 news.json
    python tools/gen-moji-daily.py --date 2026-09-06    # 指定日期
    python tools/gen-moji-daily.py --json cache.json    # 复用本地已拉取的数据（不再 ssh）
    python tools/gen-moji-daily.py --issue 242          # 手动指定期数（默认读旧页 +1）

选数逻辑：
  * 按 publishedAt 的日期部分（UTC）取目标日期新闻；栏目不足时回溯最近 48h
    （前 1~2 天）补足，控制台清单与页面时间一栏保留原始日期作为标注；
  * 总量控制在 15~25 条；各栏目保底条数见 CATS 配置；
  * 头条取目标当天最重要的 1 条（AI/机器人类优先，同分时优先无 SEO 垃圾
    后缀的标题、内容最厚重者）；
  * 同标题去重 + 相似标题抑制（字符二元组 Jaccard），避免一稿多投刷屏。

只写两个文件：site/moji_daily.html（覆盖）与留档 moji_daily_YYYYMMDD.html（首
次覆盖前由旧页自动复制，已存在则跳过）。不碰站点其他文件，不做 git 操作。
"""

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

SITE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(SITE_DIR, "moji_daily.html")
DEFAULT_SSH_HOST = "root@47.96.236.50"
DEFAULT_SSH_PATH = "/opt/li-news/li-news-project/src/data/news.json"

TZ_BJ = timezone(timedelta(hours=8))
WEEKDAY_CN = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

# 栏目配置：(数据 category, 中文栏目名, 印章字, 英文栏名, 当天不足时的保底条数)
CATS = [
    ("ai",          "AI",       "智", "ARTIFICIAL INTELLIGENCE", 6),
    ("robotics",    "机器人",   "械", "ROBOTICS",                4),
    ("geopolitics", "地缘政治", "政", "GEOPOLITICS",             4),
    ("finance",     "财经",     "财", "MARKETS",                 5),
    ("other",       "其他",     "杂", "MISCELLANY",              3),
]
CAT_LABEL = {c[0]: c[1] for c in CATS}
# 头条类别优先级（编辑偏好）：AI/机器人类优先（原版风格），其次天下大事，
# 再次财经市场。其余同分时先比标题垃圾后缀、再比内容厚重程度。
CAT_RANK = {"ai": 3.0, "robotics": 2.5, "geopolitics": 2.0, "finance": 1.5, "other": 1.0}


def junk(t):
    """标题 SEO 垃圾后缀（|、｜、_、空格-空格）计数，作同分时的质量惩罚。"""
    t = t or ""
    return t.count("|") + t.count("｜") + t.count("_") + t.count(" - ")
MIN_TOTAL, MAX_TOTAL = 15, 25
DIGEST_N = 5          # 要闻速览条数（编号 02 起）
ARCHIVE_N = 6         # 往期回顾展示份数

# 版式骨架：与 2026-08-28 第 240 期原版逐字节一致（仅数据填充位换成占位符）。
TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>墨极 MOJI · {{DATE_ISO}} 日报</title>
<meta name="description" content="墨极 · 机器手书的每日新闻。黑白两色，不着一彩，原文可溯。">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><rect width='64' height='64' rx='10' fill='%23b0392e'/><rect x='15' y='15' width='34' height='34' fill='none' stroke='%23f5f2ec' stroke-width='5'/></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Ma+Shan+Zheng&family=Noto+Serif+SC:wght@400;600;700;900&display=swap" rel="stylesheet">
<style>
/* ============ 底色与变量（日读 / 夜读） ============ */
:root {
  --paper:#f5f2ec; --card:#faf7ee; --ink:#17140f;
  --body-c:#45413a; --soft:#6f6858; --grey:#8a8578;
  --red:#b0392e; --line:rgba(23,20,15,.16); --deep-bg:rgba(23,20,15,.05);
}
body.night {
  --paper:#15110c; --card:#1d1812; --ink:#ece5d4;
  --body-c:#b2a893; --soft:#9a8f7a; --grey:#7c7462;
  --red:#d0483a; --line:rgba(236,229,212,.17); --deep-bg:rgba(236,229,212,.06);
}

* { box-sizing:border-box; margin:0; padding:0; }
html { scroll-behavior:smooth; }
body {
  background:var(--paper); color:var(--ink);
  font-family:"Noto Serif SC","Songti SC","SimSun",serif;
  min-height:100vh;
  transition:background .35s ease, color .35s ease;
}
::selection { background:var(--red); color:#f5f2ec; }
a { color:inherit; }
section[id], article[id] { scroll-margin-top:66px; }
.wrap { max-width:1180px; margin:0 auto; padding-left:clamp(18px,4vw,44px); padding-right:clamp(18px,4vw,44px); }
.num { font-family:Georgia,"Times New Roman",serif; }

/* 顶部阅读进度墨线 */
#progress { position:fixed; top:0; left:0; height:3px; width:0; background:var(--red); z-index:100; }

/* ============ 顶栏（时辰钟 / 墨相） ============ */
.topbar { background:var(--ink); color:var(--paper); font-size:11px; letter-spacing:.22em; }
.topbar-in { display:flex; justify-content:space-between; align-items:center; gap:18px; padding:7px 0; flex-wrap:wrap; }
.topbar-in > span { opacity:.85; white-space:nowrap; }
.topbar .num { letter-spacing:.12em; }

/* ============ 报头 ============ */
.masthead { text-align:center; padding:clamp(26px,4.5vh,46px) 0 24px; border-bottom:3px double var(--ink); position:relative; overflow:hidden; }
.masthead::before {
  content:"墨"; position:absolute; left:50%; top:50%;
  transform:translate(-50%,-54%);
  font-family:"Ma Shan Zheng","Kaiti SC","KaiTi",serif;
  font-size:min(30vw,300px); line-height:1;
  color:var(--ink); opacity:.045;
  pointer-events:none; user-select:none;
}
.masthead > * { position:relative; z-index:1; }
.masthead h1 {
  font-size:clamp(44px,7vw,76px); font-weight:900;
  letter-spacing:.35em; text-indent:.35em; line-height:1.1;
  display:inline-flex; align-items:flex-start;
}
.stamp {
  font-family:"Ma Shan Zheng","Kaiti SC","KaiTi",serif;
  width:.62em; height:.62em; margin-left:.18em;
  background:var(--red); color:#f6f1e6;
  display:inline-flex; align-items:center; justify-content:center;
  font-size:.42em; font-weight:400; letter-spacing:0; text-indent:0;
  border-radius:.08em; transform:rotate(-8deg) translateY(-.08em);
  box-shadow:0 3px 10px rgba(176,57,46,.3);
  user-select:none;
}
.masthead .sub { margin-top:14px; font-size:12px; letter-spacing:.42em; text-indent:.42em; color:var(--soft); }

/* 日期带（含翻期） */
.dateband {
  display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:12px;
  padding:10px 2px; border-bottom:1px solid var(--line);
  font-size:12px; letter-spacing:.15em; color:var(--soft);
}
.dateband .mid { text-align:center; }
.dateband .right { text-align:right; letter-spacing:.2em; }
.daynav { display:flex; gap:16px; }
.right.daynav { justify-content:flex-end; }
.day-link { text-decoration:none; letter-spacing:.12em; transition:color .2s ease; }
.day-link:not(.disabled):hover { color:var(--red); }
.day-link.disabled { opacity:.35; cursor:default; }

/* ============ 频道导航（吸顶） ============ */
.nav { position:sticky; top:0; z-index:60; background:var(--ink); color:var(--paper); }
.nav-in { display:flex; align-items:stretch; justify-content:space-between; gap:16px; }
.nav-links { display:flex; gap:clamp(16px,3vw,40px); overflow-x:auto; scrollbar-width:none; }
.nav-links::-webkit-scrollbar { display:none; }
.nav-links a {
  color:var(--paper); opacity:.8; text-decoration:none;
  font-size:13.5px; letter-spacing:.35em; white-space:nowrap;
  padding:13px 2px 11px; border-bottom:2px solid transparent;
  transition:opacity .25s ease, border-color .25s ease;
}
.nav-links a:hover { opacity:1; }
.nav-links a.active { opacity:1; font-weight:700; border-color:var(--red); }
.nav-extra { display:flex; align-items:center; }
.night-btn {
  display:flex; align-items:center; justify-content:center;
  background:transparent; color:inherit; cursor:pointer;
  border:1px solid rgba(245,242,236,.35); border-radius:999px;
  padding:5px 9px; transition:all .25s ease; line-height:0;
}
.night-btn:hover { background:rgba(245,242,236,.12); border-color:rgba(245,242,236,.7); transform:scale(1.06); }
/* 太极图标：黑白两色即昼夜 */
.taiji-icon {
  position:relative; display:block; width:26px; height:26px; border-radius:50%;
  background:linear-gradient(90deg, var(--ink) 50%, var(--paper) 50%);
  box-shadow:0 0 0 1.5px currentColor;
  animation:taiji-spin 16s linear infinite;
}
.taiji-icon::before, .taiji-icon::after {
  content:""; position:absolute; left:50%; transform:translateX(-50%);
  width:50%; height:50%; border-radius:50%;
}
.taiji-icon::before { top:0; background:var(--paper); box-shadow:inset 0 0 0 1px var(--ink); }
.taiji-icon::after  { bottom:0; background:var(--ink); }
.tj-eye-b, .tj-eye-w {
  position:absolute; left:50%; transform:translateX(-50%);
  width:4.5px; height:4.5px; border-radius:50%;
}
.tj-eye-b { top:4px; background:var(--ink); }
.tj-eye-w { bottom:4px; background:var(--paper); }
@keyframes taiji-spin { to { transform:rotate(360deg); } }

/* ============ 快讯滚动条 ============ */
.ticker { display:flex; align-items:stretch; border-bottom:1px solid var(--line); background:var(--card); }
.tick-label {
  flex-shrink:0; background:var(--red); color:#f6f1e6;
  font-size:11.5px; font-weight:900; letter-spacing:.4em; text-indent:.4em;
  padding:11px 14px; display:flex; align-items:center;
}
.tick-clip { overflow:hidden; flex:1; display:flex; align-items:center; }
.tick-track { display:flex; width:max-content; animation:tickmove 55s linear infinite; }
.ticker:hover .tick-track { animation-play-state:paused; }
@keyframes tickmove { to { transform:translateX(-50%); } }
.tick-track a {
  font-size:12.5px; color:var(--body-c); text-decoration:none;
  letter-spacing:.08em; white-space:nowrap; padding:10px 0; margin-right:64px;
}
.tick-track a i { color:var(--red); font-style:normal; font-size:9px; margin-right:8px; vertical-align:2px; }
.tick-track a:hover { color:var(--red); }

/* ============ 头版：头条 + 要闻速览 ============ */
.front { display:grid; grid-template-columns:minmax(0,1fr) 300px; gap:clamp(26px,4vw,52px); padding-top:clamp(24px,4vh,40px); }

.hero { position:relative; padding-bottom:10px; }
.wm {
  position:absolute; right:0; top:0;
  font-size:clamp(84px,9vw,150px); font-weight:900; line-height:.9;
  color:var(--ink); opacity:.06;
  pointer-events:none; user-select:none;
}
.meta {
  display:flex; align-items:baseline; gap:12px; flex-wrap:wrap;
  font-size:11.5px; color:var(--grey); letter-spacing:.14em; margin-bottom:12px;
}
.cat {
  font-weight:900; font-size:11.5px;
  color:var(--paper); background:var(--ink);
  padding:3px 8px 3px 10px; letter-spacing:.28em;
}
.cat.hot, .cat.top { background:var(--red); }
.time { letter-spacing:.08em; }
.src { margin-left:auto; max-width:44%; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.hero .hl {
  font-size:clamp(28px,3.6vw,42px); font-weight:900; line-height:1.4;
  letter-spacing:.01em; margin-bottom:14px; max-width:26ch;
}
.hero .hl a, .lead .hl a { color:inherit; text-decoration:none; }
.hero .hl a:hover, .lead .hl a:hover,
.card h3 a:hover { background:var(--ink); color:var(--paper); padding:2px 8px; margin-left:-8px; }
.standfirst { font-size:clamp(15.5px,1.6vw,17px); line-height:2.1; color:var(--body-c); text-align:justify; max-width:62ch; }
.foot { display:flex; align-items:baseline; gap:24px; margin-top:14px; flex-wrap:wrap; }
.origin { color:var(--red); font-weight:700; font-size:12.5px; letter-spacing:.18em; text-decoration:none; }
.origin:hover { text-decoration:underline; }
.deep-toggle {
  cursor:pointer; user-select:none;
  font-size:12px; letter-spacing:.3em; color:var(--grey);
  border-bottom:1px dashed var(--grey); padding-bottom:2px;
}
.deep-toggle:hover { color:var(--ink); border-color:var(--ink); }
.deep {
  display:none; margin-top:14px; padding:16px 20px;
  background:var(--deep-bg); border-left:3px solid var(--red);
  font-size:13.5px; line-height:2.05; color:var(--body-c);
  text-align:justify; white-space:pre-wrap;
}
.deep.open { display:block; }

/* 要闻速览侧栏 */
.digest { border-left:1px solid var(--line); padding-left:clamp(20px,2.5vw,34px); }
.digest-title {
  display:flex; align-items:center; gap:10px;
  font-size:13px; font-weight:900; letter-spacing:.45em; text-indent:.1em;
  margin-bottom:6px;
}
.digest-title .sq { width:8px; height:8px; background:var(--red); flex-shrink:0; }
.digest-item {
  display:flex; gap:12px; align-items:baseline;
  padding:13px 2px; border-bottom:1px dotted var(--line);
  text-decoration:none;
}
.digest-item .num { color:var(--red); font-weight:700; font-size:15px; min-width:24px; }
.digest-item .t { font-size:14px; font-weight:700; line-height:1.75; }
.digest-item:hover .t { color:var(--red); }

/* 栏头（频道与往期通用） */
.ch-head {
  display:flex; align-items:baseline; justify-content:space-between; gap:14px;
  border-bottom:2px solid var(--ink); padding-bottom:10px;
}
.ch-head h2 { font-size:clamp(22px,2.6vw,30px); font-weight:900; letter-spacing:.32em; }
.ch-seal {
  display:inline-flex; width:20px; height:20px; align-items:center; justify-content:center;
  background:var(--red); color:#f6f1e6; border-radius:3px;
  font-family:"Ma Shan Zheng","Kaiti SC","KaiTi",serif; font-size:12px; font-weight:400;
  transform:rotate(-6deg) translateY(-3px); margin-left:10px; letter-spacing:0; text-indent:0;
}
.ch-en { font-family:Georgia,"Times New Roman",serif; font-size:12px; color:var(--grey); letter-spacing:.22em; white-space:nowrap; }

/* ============ 频道区块 ============ */
.channel { margin-top:clamp(44px,7vh,66px); }
.lead { position:relative; padding:clamp(22px,3.5vh,32px) 0 clamp(24px,3.5vh,34px); }
.lead .hl { font-size:clamp(23px,2.7vw,33px); font-weight:900; line-height:1.45; margin-bottom:12px; max-width:32ch; }
.lead .lead-p { font-size:15px; line-height:2; color:var(--body-c); text-align:justify; max-width:64ch; }
.grid2 { display:grid; grid-template-columns:1fr 1fr; column-gap:clamp(30px,4.5vw,60px); }
.card { border-top:1px solid var(--line); padding:22px 0 26px; position:relative; }
.card h3 { font-size:clamp(18px,1.9vw,22px); font-weight:900; line-height:1.55; margin-bottom:10px; }
.card h3 a { color:inherit; text-decoration:none; }
.card p { font-size:13.5px; line-height:1.95; color:var(--body-c); text-align:justify; }
.card .no { color:var(--red); font-weight:700; font-size:13px; }
.article:target { animation:flash 1.8s ease; }
@keyframes flash { 0% { background:rgba(176,57,46,.09); } 100% { background:transparent; } }

/* ============ 往期回顾 ============ */
.archive { margin-top:clamp(44px,7vh,66px); }
.arch-grid { display:flex; flex-wrap:wrap; border-top:1px solid var(--line); border-left:1px solid var(--line); }
.arch-item {
  flex:1 1 220px; min-width:200px;
  background:var(--paper); text-decoration:none;
  padding:18px 20px 16px;
  border-right:1px solid var(--line); border-bottom:1px solid var(--line);
  transition:background .25s ease;
}
.arch-item:hover { background:var(--card); }
.arch-date { display:block; font-size:clamp(20px,2vw,26px); font-weight:700; letter-spacing:.06em; }
.arch-item:hover .arch-date { color:var(--red); }
.arch-meta { display:block; margin-top:6px; font-size:11px; letter-spacing:.2em; color:var(--grey); }
.arch-empty { padding:26px 20px; font-size:12px; letter-spacing:.3em; color:var(--grey); }

/* ============ 报尾 ============ */
.band { margin-top:clamp(60px,9vh,90px); background:var(--ink); color:var(--paper); padding:38px 0 44px; text-align:center; }
.band .band-title { font-size:20px; font-weight:900; letter-spacing:.5em; text-indent:.5em; margin-bottom:12px; }
.band p { letter-spacing:.4em; font-size:11px; opacity:.85; margin:7px 0; }
.band .band-hint { opacity:.45; letter-spacing:.3em; }
.band .stamp-mini {
  display:inline-flex; width:22px; height:22px; align-items:center; justify-content:center;
  background:var(--red); color:#f6f1e6; border-radius:4px;
  font-family:"Ma Shan Zheng","Kaiti SC","KaiTi",serif; font-size:13px; font-weight:400;
  transform:rotate(-8deg); letter-spacing:0; text-indent:0; vertical-align:-4px; margin-left:6px;
}

/* 回顶印章 */
.seal-top {
  position:fixed; right:26px; bottom:30px; z-index:80;
  width:52px; height:52px; border:none; border-radius:8px;
  background:var(--red); color:#f6f1e6; cursor:pointer;
  font-family:"Ma Shan Zheng","Kaiti SC","KaiTi",serif; font-size:17px;
  writing-mode:vertical-rl; letter-spacing:.2em; line-height:52px; text-align:center;
  transform:rotate(-6deg) scale(.5); opacity:0; pointer-events:none;
  transition:all .45s cubic-bezier(.34,1.4,.64,1);
  box-shadow:0 6px 18px rgba(0,0,0,.28);
}
.seal-top.on { opacity:1; transform:rotate(-6deg) scale(1); pointer-events:auto; }
.seal-top:hover { box-shadow:0 8px 24px rgba(176,57,46,.45); }

/* 右缘竖排署名 */
.side-mark {
  position:fixed; right:clamp(8px,1.5vw,22px); top:50%;
  transform:translateY(-50%) rotate(90deg); transform-origin:center;
  font-size:10px; letter-spacing:.4em; color:var(--ink); opacity:.28;
  white-space:nowrap; pointer-events:none; z-index:5;
}

/* ============ 响应式 ============ */
@media (max-width:1060px) {
  .front { grid-template-columns:1fr; }
  .digest { border-left:none; border-top:2px solid var(--ink); padding:22px 0 0; margin-top:6px; }
  .side-mark { display:none; }
}
@media (max-width:860px) {
  .arch-item { flex-basis:45%; }
  .wm { font-size:clamp(64px,14vw,100px); }
}
@media (max-width:680px) {
  .grid2 { grid-template-columns:1fr; }
  .arch-item { flex-basis:100%; }
  .dateband { grid-template-columns:1fr; text-align:center; }
  .dateband .mid, .dateband .right { text-align:center; }
  .daynav { justify-content:center; }
  .src { max-width:100%; }
  .seal-top { right:16px; bottom:20px; }
}
@media (prefers-reduced-motion:reduce) {
  html { scroll-behavior:auto; }
  .tick-track { animation:none; }
  .tick-clip { overflow-x:auto; }
  .seal-top { transition:none; }
  .taiji-icon { animation:none; }
  .article:target { animation:none; }
}
</style>
</head>
<body>
<div id="progress" aria-hidden="true"></div>

<!-- 顶栏 -->
<div class="topbar">
  <div class="wrap topbar-in">
    <span class="tb-left"><span class="num" id="clockTime">--:--</span>　<span id="clockHr">--</span></span>
    <span class="tb-right">❄ 雪 · 留白正好</span>
  </div>
</div>

<!-- 报头 -->
<header class="masthead">
  <div class="wrap">
    <h1>墨极<span class="stamp">印</span></h1>
    <p class="sub">机器手书 · 不着一彩 · 原文可溯</p>
  </div>
</header>
<div class="wrap">
  <div class="dateband">
    <span class="left daynav">{{DAYNAV_LEFT}}</span>
    <span class="mid num">{{DATEBAND_MID}}</span>
    <span class="right daynav">{{DAYNAV_RIGHT}}</span>
  </div>
</div>

<!-- 频道导航 -->
<nav class="nav">
  <div class="wrap nav-in">
    <div class="nav-links">
{{NAV_LINKS}}
    </div>
    <div class="nav-extra">
      <button class="night-btn" id="nightBtn" title="夜读模式（快捷键 N）" aria-label="切换夜读模式"><span class="taiji-icon" aria-hidden="true"><span class="tj-eye-b"></span><span class="tj-eye-w"></span></span></button>
    </div>
  </div>
</nav>

<!-- 快讯 -->
<div class="ticker" aria-label="快讯">
  <span class="tick-label">快讯</span>
  <div class="tick-clip">
    <div class="tick-track">
{{TICKER_ITEMS}}
    </div>
  </div>
</div>

<main class="wrap">
{{FRONT_AND_CHANNELS}}
</main>

<!-- ===== 往期回顾 ===== -->
<section id="archive" class="archive wrap">
  <div class="ch-head">
    <h2>往期回顾<span class="ch-seal">档</span></h2>
    <span class="ch-en">ARCHIVE</span>
  </div>
  <div class="arch-grid">
{{ARCHIVE_GRID}}
  </div>
</section>

<!-- 报尾 -->
<footer class="band">
  <div class="wrap">
    <p class="band-title">墨极<span class="stamp-mini">印</span></p>
    <p>机器手书 · 旁注皆机器所拟 · 原文可溯</p>
    <p>距明日 09:00 报讯 · <span class="num" id="cdNum2">--:--:--</span></p>
    <p class="band-hint num">J / K 换条 · T 回顶 · N 夜读</p>
  </div>
</footer>

<button class="seal-top" id="sealTop" title="回到卷首">回顶</button>
<span class="side-mark">MOJI DAILY · 墨极编辑部 · 原文可溯</span>

<script>
(function(){
  var body = document.body;

  /* 夜读模式（记忆偏好） */
  try { if (localStorage.getItem("moji-night") === "1") body.classList.add("night"); } catch(e) {}
  function toggleNight(){
    body.classList.toggle("night");
    try { localStorage.setItem("moji-night", body.classList.contains("night") ? "1" : "0"); } catch(e) {}
  }
  document.getElementById("nightBtn").addEventListener("click", toggleNight);

  /* 展墨 / 收墨 */
  document.addEventListener("click", function(e){
    var t = e.target;
    if (t.classList && t.classList.contains("deep-toggle")) {
      var art = t.closest("article") || t.closest(".hero");
      var d = art && art.querySelector(".deep");
      if (d) {
        d.classList.toggle("open");
        t.textContent = d.classList.contains("open") ? "收墨 ▲" : "展墨 ▼";
      }
    }
  });

  /* 时辰钟 */
  var HRS = ["子时","丑时","寅时","卯时","辰时","巳时","午时","未时","申时","酉时","戌时","亥时"];
  function tickClock(){
    var n = new Date();
    var hh = String(n.getHours()).padStart(2,"0");
    var mm = String(n.getMinutes()).padStart(2,"0");
    document.getElementById("clockTime").textContent = hh + ":" + mm;
    document.getElementById("clockHr").textContent = HRS[Math.floor(((n.getHours()+1)%24)/2)];
  }
  tickClock(); setInterval(tickClock, 15000);

  /* 距明日报讯（09:00）倒计时 */
  function tickCountdown(){
    var now = new Date();
    var next = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 9, 0, 0);
    if (now.getHours() >= 9) next = new Date(now.getFullYear(), now.getMonth(), now.getDate()+1, 9, 0, 0);
    var diff = Math.max(0, next - now);
    var h = String(Math.floor(diff/3600000)).padStart(2,"0");
    var m = String(Math.floor(diff%3600000/60000)).padStart(2,"0");
    var s = String(Math.floor(diff%60000/1000)).padStart(2,"0");
    document.getElementById("cdNum2").textContent = h + ":" + m + ":" + s;
  }
  tickCountdown(); setInterval(tickCountdown, 1000);

  /* 阅读进度 + 导航高亮 + 回顶印章 */
  var bar = document.getElementById("progress");
  var seal = document.getElementById("sealTop");
  var arts = Array.prototype.slice.call(document.querySelectorAll("article[data-num]"));
  var navLinks = Array.prototype.slice.call(document.querySelectorAll(".nav-links a"));
  var SPY = {{SPY_IDS}};

  function onScroll(){
    var docH = document.documentElement.scrollHeight - window.innerHeight;
    var pct = Math.min(100, Math.max(0, Math.round(window.scrollY / (docH || 1) * 100)));
    bar.style.width = pct + "%";

    var cur = SPY[0];
    SPY.forEach(function(id){
      var el = document.getElementById(id);
      if (el && el.getBoundingClientRect().top < window.innerHeight * 0.42) cur = id;
    });
    navLinks.forEach(function(a){ a.classList.toggle("active", a.getAttribute("href") === "#" + cur); });

    seal.classList.toggle("on", window.scrollY > window.innerHeight * 0.9);
  }
  window.addEventListener("scroll", onScroll, { passive:true });
  onScroll();
  seal.addEventListener("click", function(){ window.scrollTo({ top:0, behavior:"smooth" }); });

  /* 键盘导航：J/K 换条 · T 回顶 · N 夜读 */
  document.addEventListener("keydown", function(e){
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    var k = e.key.toLowerCase();
    if (k === "t") {
      window.scrollTo({ top:0, behavior:"smooth" });
    } else if (k === "n") {
      toggleNight();
    } else if (k === "j" || k === "k") {
      var curIdx = -1;
      arts.forEach(function(a, i){
        if (curIdx === -1 && a.getBoundingClientRect().top > 70) curIdx = i;
      });
      var target;
      if (k === "j") target = Math.max(0, curIdx === -1 ? arts.length - 1 : curIdx);
      else target = Math.max(0, (curIdx === -1 ? arts.length : curIdx) - 2);
      if (arts[target]) arts[target].scrollIntoView({ behavior:"smooth", block:"start" });
    }
  });
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- 基础工具 --
def esc(s):
    return html.escape(s or "", quote=True)


def parse_iso(s):
    s = (s or "").strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def bj_time(item):
    """页面时间：北京时间（原版 06:23Z 显示为 14:23 的口径）。"""
    dt = parse_iso(item["publishedAt"]).astimezone(TZ_BJ)
    return "%d月%d日 %s" % (dt.month, dt.day, dt.strftime("%H:%M"))


def substance(it):
    return len(it.get("deepDive") or "") + len(it.get("summary") or "")


def norm_title(t):
    n = re.sub(r"[\W_]+", "", (t or "").lower())
    return n or (t or "")


def bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)}


def similar(a, b, th):
    A, B = bigrams(norm_title(a)), bigrams(norm_title(b))
    if not A or not B:
        return False
    return len(A & B) / len(A | B) >= th


def truncate(s, n):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n].rstrip() + "…"


def excerpt(s, target=70, cap=160):
    """摘要导语：按句切分，累积到 target 字左右为止（不超过 cap）。"""
    s = re.sub(r"\s+", " ", s or "").strip()
    if len(s) <= cap:
        return s
    out, n = "", 0
    for m in re.finditer(r"[^。！？!?]*[。！？!?]", s):
        out += m.group(0)
        n += len(m.group(0))
        if n >= target:
            break
    out = out.strip() or s[:cap]
    return out[:cap]


def clean_deep(s):
    """AI 解读正文轻量清洗：去 markdown 标记与『AI 解读』框题，保留换行。"""
    lines = []
    for ln in (s or "").splitlines():
        st = ln.strip()
        st = re.sub(r"^#{1,6}\s*", "", st)
        st = st.replace("**", "").replace("`", "")
        if st in ("AI 解读", "AI解读", "---", "***", ""):
            if st == "" and lines and lines[-1] != "":
                lines.append("")
            continue
        lines.append(st)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


# ---------------------------------------------------------------- 数据获取 --
def fetch_news(args):
    if args.json:
        with open(args.json, encoding="utf-8") as f:
            return json.load(f)
    cache = os.path.join(tempfile.gettempdir(), "moji_news_cache.json")
    print("[fetch] ssh %s 'cat %s' -> %s" % (args.ssh_host, args.ssh_path, cache))
    with open(cache, "w", encoding="utf-8", newline="\n") as f:
        subprocess.run(["ssh", args.ssh_host, "cat " + args.ssh_path],
                       stdout=f, check=True, timeout=120)
    with open(cache, encoding="utf-8") as f:
        return json.load(f)


def dedupe(items):
    """同标题去重（保留内容最厚重的一条），返回新列表。"""
    best = {}
    for it in items:
        k = norm_title(it.get("title", ""))
        if k not in best or substance(it) > substance(best[k]):
            best[k] = it
    return list(best.values())


# ---------------------------------------------------------------- 选数逻辑 --
def bucket_of(it, target):
    d = parse_iso(it["publishedAt"]).date()
    delta = (target - d).days
    return delta if 0 <= delta <= 2 else None   # 0=当天，1/2=48h 回溯窗


def order_key(it):
    return (it["_bucket"],
            0 if it.get("importance") == "hot" else 1,
            junk(it.get("title")),
            -parse_iso(it["publishedAt"]).timestamp(),
            -substance(it))


def pick_pool(pool, want, banned_titles, th):
    """按 order_key 依次取，跳过与已选/禁用标题相似者。"""
    out, banned = [], list(banned_titles)
    for it in sorted(pool, key=order_key):
        if len(out) >= want:
            break
        if any(similar(it["title"], t, th) for t in banned):
            continue
        out.append(it)
        banned.append(it["title"])
    return out


def select(items, target, th):
    win = []
    for it in items:
        b = bucket_of(it, target)
        if b is not None:
            win.append(dict(it, _bucket=b))
    if not win:
        raise SystemExit("选数失败：目标日期前后 48h 内没有任何新闻")
    by_cat = {}
    for it in win:
        by_cat.setdefault(it.get("category", "other").lower(), []).append(it)
    for c in by_cat:
        by_cat[c] = dedupe(by_cat[c])

    # ---- 头条：当天优先，AI/机器人类优先，其次内容最厚重 ----
    def hero_key(it):
        return (it["_bucket"],
                0 if it.get("importance") == "hot" else 1,
                -CAT_RANK.get(it.get("category", "").lower(), 0.0),
                junk(it.get("title")),
                -substance(it))
    hero = sorted(win, key=hero_key)[0]
    hero_cat = hero.get("category", "other").lower()

    # ---- 各栏目：当天全收，不足回溯补到保底条数 ----
    sections, flat = [], []
    for key, label, seal, en, want in CATS:
        pool = [it for it in by_cat.get(key, []) if it is not hero]
        banned = [hero["title"]] if key == hero_cat else []
        picked = pick_pool(pool, want, banned, th)
        if picked:
            sections.append(dict(key=key, label=label, seal=seal, en=en, items=picked))
            flat.extend(picked)

    # ---- 总量微调：不足 MIN_TOTAL 跨栏目续补 ----
    def total_n():
        return 1 + sum(len(s["items"]) for s in sections)

    if total_n() < MIN_TOTAL:
        for key, label, seal, en, _want in CATS:
            sec = next((s for s in sections if s["key"] == key), None)
            if sec is None:
                continue
            need = MIN_TOTAL - total_n()
            banned = [i["title"] for i in sec["items"]]
            if key == hero_cat:
                banned.append(hero["title"])
            pool = [i for i in by_cat.get(key, []) if i is not hero and i not in sec["items"]]
            extra = pick_pool(pool, need, banned, th)
            sec["items"].extend(extra)
            flat.extend(extra)
            if total_n() >= MIN_TOTAL:
                break

    # ---- 总量微调：超出 MAX_TOTAL 时从尾部回溯条裁起 ----
    while total_n() > MAX_TOTAL:
        victim = None
        for sec in reversed(sections):
            for it in reversed(sec["items"]):
                if it["_bucket"] != 0:
                    victim = (sec, it)
                    break
            if victim:
                break
        if not victim:
            break
        victim[0]["items"].remove(victim[1])
        flat.remove(victim[1])
    return hero, [s for s in sections if s["items"]], flat


# ---------------------------------------------------------------- 渲染 ------
def foot_block(url, deep_text):
    return (
        '      <div class="foot">\n'
        '        <a class="origin" href="%s" target="_blank" rel="noopener">阅读原文 ↗</a>\n'
        '      <span class="deep-toggle">展墨 ▼</span>\n'
        '        <div class="deep">%s</div>\n'
        '      </div>' % (esc(url), esc(deep_text))
    )


def build_front(hero, digest_items):
    deep = clean_deep(hero.get("deepDive") or hero.get("summary") or "")
    cat = CAT_LABEL.get(hero.get("category", "other").lower(), "其他")
    lines = [
        '  <!-- ===== 头版 ===== -->',
        '  <section id="front" class="front">',
        '    <div class="hero" id="hero">',
        '      <span class="wm num" aria-hidden="true">01</span>',
        '      <div class="meta">',
        '        <span class="cat top">头条</span><span class="cat">%s</span>' % esc(cat),
        '        <span class="time num">%s</span>' % bj_time(hero),
        '        <span class="src">源 · %s</span>' % esc(hero.get("source", "")),
        '      </div>',
        '      <h2 class="hl"><a href="%s" target="_blank" rel="noopener">%s</a></h2>'
        % (esc(hero.get("sourceUrl", "")), esc(hero["title"])),
        '      <p class="standfirst">%s</p>' % esc(excerpt(hero.get("summary", ""))),
        foot_block(hero.get("sourceUrl", ""), deep),
        '    </div>',
        '',
        '    <aside class="digest">',
        '      <p class="digest-title"><span class="sq"></span>要闻速览</p>',
    ]
    for it in digest_items:
        lines.append(
            '      <a class="digest-item" href="#%s"><span class="num">%02d</span>'
            '<span class="t">%s</span></a>'
            % (it["_id"], it["_num"], esc(truncate(it["title"], 30))))
    lines += ['    </aside>', '  </section>']
    return "\n".join(lines)


def build_channel(sec):
    items = sec["items"]
    lead, cards = items[0], items[1:]
    lines = [
        '',
        '  <!-- ===== %s ===== -->' % sec["label"],
        '  <section id="sec-%s" class="channel">' % sec["key"],
        '    <div class="ch-head">',
        '      <h2>%s<span class="ch-seal">%s</span></h2>' % (esc(sec["label"]), sec["seal"]),
        '      <span class="ch-en">%s · %d 篇</span>' % (sec["en"], len(items)),
        '    </div>',
    ]
    it = lead
    deep = clean_deep(it.get("deepDive") or it.get("summary") or "")
    hot = ' hot' if it.get("importance") == "hot" else ''
    lines += [
        '    <article class="lead article" id="%s" data-num="%d">' % (it["_id"], it["_num"]),
        '      <span class="wm num" aria-hidden="true">%02d</span>' % it["_num"],
        '      <div class="meta">',
        '        <span class="no num">%02d</span><span class="cat%s">%s</span>'
        % (it["_num"], hot, esc(sec["label"])),
        '        <span class="time num">%s</span>' % bj_time(it),
        '        <span class="src">源 · %s</span>' % esc(it.get("source", "")),
        '      </div>',
        '      <h2 class="hl"><a href="%s" target="_blank" rel="noopener">%s</a></h2>'
        % (esc(it.get("sourceUrl", "")), esc(it["title"])),
        '      <p class="lead-p">%s</p>' % esc(excerpt(it.get("summary", ""))),
        foot_block(it.get("sourceUrl", ""), deep),
        '    </article>',
    ]
    if cards:
        lines.append('    <div class="grid2">')
        for it in cards:
            deep = clean_deep(it.get("deepDive") or it.get("summary") or "")
            hot = ' hot' if it.get("importance") == "hot" else ''
            lines += [
                '      <article class="card article" id="%s" data-num="%d">' % (it["_id"], it["_num"]),
                '        <div class="meta">',
                '          <span class="no num">%02d</span><span class="cat%s">%s</span>'
                % (it["_num"], hot, esc(sec["label"])),
                '          <span class="time num">%s</span>' % bj_time(it),
                '          <span class="src">源 · %s</span>' % esc(it.get("source", "")),
                '        </div>',
                '        <h3><a href="%s" target="_blank" rel="noopener">%s</a></h3>'
                % (esc(it.get("sourceUrl", "")), esc(it["title"])),
                '        <p>%s</p>' % esc(excerpt(it.get("summary", ""))),
                foot_block(it.get("sourceUrl", ""), deep),
                '      </article>',
            ]
        lines.append('    </div>')
    lines.append('  </section>')
    return "\n".join(lines)


def build_ticker(hero, flat):
    rows = [("hero", hero["title"])] + [(it["_id"], it["title"]) for it in flat]
    one = "\n".join('        <a href="#%s"><i>◆</i>%s</a>' % (aid, esc(truncate(t, 32)))
                    for aid, t in rows)
    return one + "\n" + one          # 跑马灯无缝循环需两份拷贝


def build_nav(sections):
    rows = ['      <a href="#front" class="active">头条</a>']
    rows += ['      <a href="#sec-%s">%s</a>' % (s["key"], esc(s["label"])) for s in sections]
    rows.append('      <a href="#archive">往期</a>')
    return "\n".join(rows)


def build_archive(site_dir, target):
    pats = []
    try:
        names = os.listdir(site_dir)
    except OSError:
        names = []
    found = []
    for name in names:
        m = re.match(r"^墨极·(\d{4})(\d{2})(\d{2})\.html$", name)
        if m:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if d != target:
                found.append((d, name))
    for d, name in sorted(found, reverse=True)[:ARCHIVE_N]:
        cnt = ""
        try:
            with open(os.path.join(site_dir, name), encoding="utf-8") as f:
                m = re.search(r"第 \d+ 期 · (\d+) 条", f.read())
            if m:
                cnt = " · %s 条" % m.group(1)
        except OSError:
            pass
        pats.append(
            '    <a class="arch-item" href="%s"><span class="arch-date num">%s</span>'
            '<span class="arch-meta">%d · %s%s</span></a>'
            % (esc(name), d.strftime("%m.%d"), d.year, WEEKDAY_CN[d.weekday()], cnt))
    return "\n".join(pats)


def render(hero, sections, target, issue, site_dir):
    flat = [it for s in sections for it in s["items"]]
    for i, it in enumerate(flat, start=2):
        it["_num"] = i
        it["_id"] = "a%d" % i
    hero["_num"], hero["_id"] = 1, "hero"
    total = len(flat) + 1

    prev = target - timedelta(days=1)
    left = ('<a class="day-link num" href="archive.html">← %s 前一日</a>'
            % prev.strftime("%m.%d"))
    if target <= date.today():
        right = '<span class="day-link num disabled">后一日 →</span>'
    else:
        nxt = target + timedelta(days=1)
        right = ('<a class="day-link num" href="archive.html">→ %s 后一日</a>'
                 % nxt.strftime("%m.%d"))
    mid = "%s %s · 第 %d 期 · %d 条" % (
        target.isoformat(), WEEKDAY_CN[target.weekday()], issue, total)

    spy = ["front"] + ["sec-" + s["key"] for s in sections] + ["archive"]

    out = TEMPLATE
    repl = {
        "{{DATE_ISO}}": target.isoformat(),
        "{{DAYNAV_LEFT}}": left,
        "{{DATEBAND_MID}}": esc(mid),
        "{{DAYNAV_RIGHT}}": right,
        "{{NAV_LINKS}}": build_nav(sections),
        "{{TICKER_ITEMS}}": build_ticker(hero, flat),
        "{{FRONT_AND_CHANNELS}}": (build_front(hero, flat[:DIGEST_N])
                                   + "".join(build_channel(s) for s in sections)),
        "{{ARCHIVE_GRID}}": build_archive(site_dir, target),
        "{{SPY_IDS}}": '["' + '","'.join(spy) + '"]',
    }
    for k, v in repl.items():
        assert k in out, "template missing token " + k
        out = out.replace(k, v)
    assert "{{" not in out, "unreplaced token remains"
    return out, total


# ---------------------------------------------------------------- 自验 ------
def verify(text, target, issue, total, sections, prev_date, prev_issue):
    ok = True

    def chk(name, cond, hard=True):
        nonlocal ok
        print("  [%s] %s" % ("PASS" if cond else "FAIL", name))
        if hard and not cond:
            ok = False

    chk("期数条含「第 %d 期」" % issue, ("第 %d 期" % issue) in text)
    chk("含目标日期 %s" % target.isoformat(), target.isoformat() in text)
    chk("总条数标注「· %d 条」" % total, ("· %d 条" % total) in text)
    for s in sections:
        chk("栏目节 sec-%s 存在且入导航" % s["key"],
            ('id="sec-%s"' % s["key"]) in text and ('href="#sec-%s"' % s["key"]) in text)
    chk("头条锚点 #hero", 'id="hero"' in text and 'href="#hero"' in text)
    chk("正文编号锚点 a2..a%d 齐全" % total,
        all(('id="a%d"' % i) in text and ('href="#a%d"' % i) in text
            for i in range(2, total + 1)))
    chk("跑马灯两份拷贝（%d 条）" % (total * 2), text.count("<i>◆</i>") == total * 2)
    chk("无占位符残留", "{{" not in text)
    # 残留旧数据文本（硬性：破折号日期/期数/前一日链接；软性：中文日期，正文可能合法引用）
    if prev_date and prev_date != target:
        chk("无残留旧日期 %s" % prev_date.isoformat(), prev_date.isoformat() not in text)
        chk("无残留旧期数「第 %d 期」" % prev_issue, ("第 %d 期" % prev_issue) not in text)
        chk("无残留旧翻期链接", ("%s 前一日" % (prev_date - timedelta(days=1)).strftime("%m.%d"))
            not in text)
        soft = "%d月%d日" % (prev_date.month, prev_date.day)
        chk("旧中文日期「%s」未出现（正文合法引用除外，仅提示）" % soft,
            soft not in text, hard=False)
    # 标签配平
    for tag in ("div", "section", "article", "aside", "nav", "main", "span", "a", "p", "h2", "h3"):
        o = len(re.findall(r"<%s[\s>]" % tag, text))
        c = text.count("</%s>" % tag)
        chk("<%s> 标签配平（%d/%d）" % (tag, o, c), o == c)
    return ok


# ---------------------------------------------------------------- 主流程 ---
def parse_prev(out_path):
    """读旧版页面：期数（默认 +1）与日期（留档文件名用）。"""
    if not os.path.exists(out_path):
        return None, None
    with open(out_path, encoding="utf-8") as f:
        t = f.read()
    m1 = re.search(r"第\s*(\d+)\s*期", t)
    m2 = re.search(r"(\d{4}-\d{2}-\d{2})\s*星期", t)
    return (int(m1.group(1)) if m1 else None,
            date.fromisoformat(m2.group(1)) if m2 else None)


def main():
    ap = argparse.ArgumentParser(description="墨极日报生成器")
    ap.add_argument("--date", default=date.today().isoformat(), help="目标日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--issue", type=int, default=None, help="期数（默认=旧页期数+1）")
    ap.add_argument("--json", default=None, help="本地 news.json 路径（给了就不再 ssh）")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出 HTML 路径")
    ap.add_argument("--site", default=SITE_DIR, help="站点目录（扫往期文件用）")
    ap.add_argument("--ssh-host", default=DEFAULT_SSH_HOST)
    ap.add_argument("--ssh-path", default=DEFAULT_SSH_PATH)
    ap.add_argument("--dupe-threshold", type=float, default=0.22,
                    help="相似标题抑制阈值（字符二元组 Jaccard）")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    target = date.fromisoformat(args.date)
    prev_issue, prev_date = parse_prev(args.out)
    if args.issue:
        issue = args.issue
    else:
        # 期数口径 = 年内第几天（与 archive 页 issueOf 一致：8/28=240、9/6=249）
        issue = target.timetuple().tm_yday

    data = fetch_news(args)
    items = data["items"]
    print("[data] lastUpdated=%s, items=%d" % (data.get("lastUpdated"), len(items)))

    hero, sections, flat = select(items, target, args.dupe_threshold)
    total = len(flat) + 1

    # 覆盖前留档：旧版（与目标日期不同日时）复制为 moji_daily_YYYYMMDD.html
    if prev_date and prev_date != target \
            and os.path.abspath(args.out) == os.path.abspath(DEFAULT_OUT):
        backup = os.path.join(args.site, "moji_daily_%s.html" % prev_date.strftime("%Y%m%d"))
        if not os.path.exists(backup):
            shutil.copy2(args.out, backup)
            print("[backup] %s -> %s" % (args.out, backup))
        else:
            print("[backup] %s 已存在，跳过" % backup)

    html_text, total = render(hero, sections, target, issue, args.site)
    with open(args.out, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(html_text)
    print("[write] %s (%d bytes)" % (args.out, os.path.getsize(args.out)))

    # 控制台选闻清单（·回溯=48h 补入，标注原始日期）
    print("\n=== 墨极日报 %s · 第 %d 期 · %d 条 ===" % (target.isoformat(), issue, total))
    print("头条 01 [%s%s] %s" % (CAT_LABEL.get(hero["category"], hero["category"]),
                                 "" if hero["_bucket"] == 0 else " ·回溯",
                                 hero["title"]))
    for s in sections:
        print("-- %s（%d 篇）--" % (s["label"], len(s["items"])))
        for it in s["items"]:
            print("  %02d [%s%s] %s" % (it["_num"], s["label"],
                                        "" if it["_bucket"] == 0
                                        else " ·回溯%s" % parse_iso(it["publishedAt"]).date(),
                                        it["title"]))

    print("\n=== 自验 ===")
    ok = verify(open(args.out, encoding="utf-8").read(), target, issue, total, sections,
                prev_date, prev_issue)
    if not ok:
        sys.exit(1)
    print("自验全部通过。")


if __name__ == "__main__":
    main()
