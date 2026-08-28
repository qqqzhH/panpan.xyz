/* ============================================================
   标签页彩蛋 + 深夜提示条 + 黑客模式 (纯原生 JS 版)
   同步自木子新闻 Next 版 · TabTitleTrick.tsx + EasterEggs.tsx
   ============================================================ */
(function () {
  "use strict";

  /* ---------- 标签页彩蛋 (切走/切回标题，每天随机一组) ---------- */
  var TITLES = [
    // —— 原创经典组 ——
    { leave: "(╯°□°)╯ 页面飞走了", back: "( ◦ °ω° ◦ ) 飞回来了~" },
    { leave: "〔ﾟДﾟ〕 页面不见了！", back: "(ﾟωﾟ) 还在！" },
    { leave: "Σ(°△°|||) 页面已失踪", back: "ヽ(°▽°)ノ 找到你啦~" },
    { leave: "(×﹏×) 页面崩溃惹", back: "( °▽°*) 恢复成功~" },
    { leave: "(°A°) 页面崩溃啦", back: "(>ω<) 噫又好了~" },
    // —— 创意组 ——
    { leave: "(つω⊂) 你快回来", back: "ヽ(°▽°)ノ 你终于回来了" },
    { leave: "(×﹏×) 你别走啊，新闻还没看完", back: "( °ω° ) 你总算回来了，我等了好久" },
    { leave: "(°ω°)? 偷偷摸摸跑哪去了？", back: "(^▽^) 可算把你盼回来了" },
    { leave: "(^-^)/ 去去就回", back: "(^-^) 回来了就请坐" },
    { leave: "(>_<) 页面在等你回家", back: "(=^▽^=) 主人，你到家了" },
    { leave: "(つ﹏⊂) 别丢下我", back: "(つ°▽°)つ 抱抱你" },
    // —— 新增组 ——
    { leave: "(°ω°)? 哼，你是不是背着我逛别的站了", back: "( ^▽^ ) 算了算了，回来就好" },
    { leave: "(>_<) 摸鱼被老板抓了吗", back: "(^▽^)/ 平安回来，继续摸鱼" },
    { leave: "(=^ω^=)喵？主人去哪了", back: "(=^ω^=)喵！蹭蹭你" },
    { leave: "(°ω°)〔侦探模式〕线索中断…", back: "ヽ(°▽°)ノ〔案件告破〕目标回来了" },
    { leave: "【掉线】(×﹏×)", back: "ヽ(°▽°)ノ【重新连接成功】" },
    { leave: "(ﾟωﾟ)? 你是不是去刷抖音了", back: "(°▽°) 玩够了吗？新闻都凉了" },
    { leave: "(×﹏×) 你背着我看别的新闻？", back: "( ^ω^ ) 哼，原谅你了" },
    { leave: "(つω⊂) 别走嘛再看一眼", back: "(°▽°*) 就知道你舍不得我" },
    { leave: "【系统】目标失联(×﹏×)", back: "ヽ(°▽°)ノ【系统】目标已归位" }
  ];
  var origTitle = document.title;
  // 每天随机选一组（跟 Next 版同算法：年月日数字求和 % 组数）
  var d = new Date();
  var ymd = "" + d.getFullYear() + (d.getMonth() + 1) + d.getDate();
  var idx = 0;
  for (var i = 0; i < ymd.length; i++) idx += parseInt(ymd[i], 10);
  var t = TITLES[idx % TITLES.length];
  var timeout;

  function onVisibility() {
    clearTimeout(timeout);
    document.title = document.hidden ? t.leave : t.back;
    if (!document.hidden) {
      timeout = setTimeout(function () { document.title = origTitle; }, 3000);
    }
  }
  document.addEventListener("visibilitychange", onVisibility);

  /* ---------- 深夜提示条 (22点-6点) ---------- */
  function checkNight() {
    var h = new Date().getHours();
    var el = document.getElementById("night-bar");
    if (!el) return;
    if (h >= 22 || h < 6) {
      el.classList.remove("hidden");
    } else {
      el.classList.add("hidden");
    }
  }
  checkNight();
  var nightTimer = setInterval(checkNight, 60000);

  /* ---------- 黑客模式 (Ctrl+H 切换) ---------- */
  var hacker = false;
  function onKey(e) {
    if (e.ctrlKey && (e.key === "h" || e.key === "H")) {
      e.preventDefault();
      hacker = !hacker;
      document.documentElement.classList.toggle("hacker-mode", hacker);
      var tag = document.getElementById("hacker-tag");
      if (tag) tag.style.display = hacker ? "block" : "none";
    }
  }
  window.addEventListener("keydown", onKey);

  /* ---------- 写入深夜提示条 + 黑客指示器 (若页面无则注入) ---------- */
  function ensureEls() {
    if (!document.getElementById("night-bar")) {
      var nb = document.createElement("div");
      nb.id = "night-bar";
      nb.className = "night-bar";
      nb.innerHTML =
        '<span>🌙</span> 深夜了，还在看？注意休息哦 <span class="night-face">(´･ω･`)</span>';
      document.body.appendChild(nb);
    }
    if (!document.getElementById("hacker-tag")) {
      var ht = document.createElement("div");
      ht.id = "hacker-tag";
      ht.className = "hacker-tag";
      ht.style.display = "none";
      ht.textContent = "HACKER MODE • Ctrl+H";
      document.body.appendChild(ht);
    }
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ensureEls);
  } else {
    ensureEls();
  }
})();
