/* 口腔文献日课 — reads data/index.json + data/daily/<date>.json */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const esc = (v) =>
    String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const LS = {
    read: "dr.read.v1",
    saved: "dr.saved.v1",
    dismissed: "dr.dismissed.v1",
  };
  const loadSet = (k) => new Set(JSON.parse(localStorage.getItem(k) || "[]"));
  const store = {
    read: loadSet(LS.read),
    saved: loadSet(LS.saved),
    dismissed: loadSet(LS.dismissed),
  };
  const persist = () => {
    localStorage.setItem(LS.read, JSON.stringify([...store.read]));
    localStorage.setItem(LS.saved, JSON.stringify([...store.saved]));
    localStorage.setItem(LS.dismissed, JSON.stringify([...store.dismissed]));
  };

  const state = { index: null, day: null, date: null };

  const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
  const LEVEL_LABELS = ["病例", "体外", "动物", "横断", "病对", "队列", "RCT", "系统评价"];

  const fmtDate = (iso) => {
    if (!iso) return "——";
    const [y, m, d] = iso.split("-");
    return `${y}<span class="sep">.</span>${m}<span class="sep">.</span>${d}`;
  };
  const weekdayOf = (iso) => {
    const dt = new Date(`${iso}T08:00:00`);
    return Number.isNaN(dt.getTime()) ? "" : WEEKDAYS[dt.getDay()];
  };

  async function boot() {
    bindChrome();
    try {
      const res = await fetch("data/index.json", { cache: "no-store" });
      if (!res.ok) throw new Error(`index.json ${res.status}`);
      state.index = await res.json();
    } catch (err) {
      $("#lede").textContent = "还没有生成数据。先在本地运行 python -m pipeline.main，或等 GitHub Actions 跑完第一班。";
      $("#kicker").textContent = "NO DATA";
      console.error(err);
      return;
    }
    renderDateOptions();
    const wanted = new URLSearchParams(location.search).get("date");
    const date = wanted && state.index.days.some((d) => d.date === wanted) ? wanted : state.index.latest;
    if (date) await loadDay(date);
    else {
      $("#lede").textContent = "今天没有可展示的文献。";
    }
  }

  function renderDateOptions() {
    const sel = $("#dateSelect");
    sel.innerHTML = (state.index.days || [])
      .map((d) => `<option value="${esc(d.date)}">${esc(d.date)}　${esc(weekdayOf(d.date))}</option>`)
      .join("");
    sel.addEventListener("change", () => loadDay(sel.value));
  }

  async function loadDay(date) {
    state.date = date;
    $("#dateSelect").value = date;
    const url = new URL(location.href);
    url.searchParams.set("date", date);
    history.replaceState(null, "", url);
    try {
      const res = await fetch(`data/daily/${date}.json`, { cache: "no-store" });
      if (!res.ok) throw new Error(`daily ${res.status}`);
      state.day = await res.json();
    } catch (err) {
      $("#lede").textContent = `${date} 的数据读取失败。`;
      console.error(err);
      return;
    }
    renderAll();
  }

  function shownPapers() {
    const d = state.day;
    if (!d) return [];
    return [d.must_read, ...(d.scan || [])].filter(Boolean);
  }

  function renderAll() {
    const d = state.day;
    document.title = `${d.date} · 口腔文献日课`;
    renderMasthead(d);
    renderMust(d);
    renderScan(d);
    renderWeekly(d);
    renderBacklog(d);
    renderFooter(d);
    updateProgress();
    requestAnimationFrame(() => document.body.classList.add("ready"));
  }

  function renderMasthead(d) {
    $("#kicker").textContent = `${weekdayOf(d.date)} / ${d.ai ? "AI 排序" : "确定性排序"}`;
    $("#dateMain").innerHTML = fmtDate(d.date);
    const stats = d.stats || {};
    const shown = shownPapers().length;
    const scans = (d.scan || []).length;
    const minutes = d.must_read?.deep?.reading_minutes
      ? Number(d.must_read.deep.reading_minutes) + Math.max(0, scans) * 2
      : 20;
    if (shown === 0) {
      $("#lede").textContent = "今天没有值得占用你阅读位的论文。这是正常结果，不是故障。";
    } else if (d.ai) {
      $("#lede").innerHTML = `今天从 <em>${esc(stats.fetched ?? stats.gated ?? "?")}</em> 篇新论文里留下 ${shown} 篇：1 篇精读，${scans} 篇速览。读完约 ${minutes} 分钟。`;
    } else {
      $("#lede").innerHTML = `今天从 <em>${esc(stats.fetched ?? stats.gated ?? "?")}</em> 篇新论文里按规则留下 ${shown} 篇。模型未启用，所以没有精读卡与点评。`;
    }
    const raw = stats.raw ?? stats.fetched;
    $("#funnel").innerHTML = `
      <span><b>${esc(raw ?? "?")}</b> 篇候选</span><span class="arrow">→</span>
      <span><b>${esc(stats.gated ?? "?")}</b> 篇过筛</span><span class="arrow">→</span>
      <span><b>${shown}</b> 篇留下</span>
      <span class="out">${shown ? `约 ${minutes} 分钟` : "0 分钟"}</span>
      <span style="margin-left:auto">屏蔽 ${esc(stats.raw_dropped_type ?? 0)} 条社论/病例 · 无摘要 ${esc(stats.no_abstract ?? 0)} 条</span>`;

    const notice = $("#notice");
    notice.innerHTML = d.ai
      ? ""
      : `<div class="banner"><b>未接入模型</b><span>这一班只有确定性排序：没有精读卡、没有「与我的关系」点评。在仓库 Secrets 里加上 AGNES_API_KEY，下一班会自动补上。</span></div>`;
  }

  function probe(level, label) {
    const lv = Math.max(0, Math.min(7, Number(level) || 0));
    const levels = LEVEL_LABELS.map((name, i) => {
      const pos = (i / 7) * 100;
      const active = i === lv ? " on" : "";
      return `<span class="lvl${active}" style="top:${100 - pos}%">${i}</span>`;
    }).join("");
    const pos = (lv / 7) * 100;
    return `
      <div class="probe" aria-hidden="true">
        <div class="probe-scale">${levels}
          <div class="probe-marker" style="top:${100 - pos}%"></div>
        </div>
        <p class="probe-caption">${esc(label)}<br>证据强度 ${lv}/7</p>
      </div>`;
  }

  function scoreBlock(score) {
    if (!score || score.final == null) return "";
    const rows = [
      ["匹配", score.match],
      ["新颖", score.novelty],
      ["证据", score.rigor],
      ["影响", score.impact],
      ["迁移", score.transfer],
    ].filter(([, v]) => v != null);
    if (!rows.length) return "";
    return `<div class="breakdown">${rows
      .map(([k, v]) => `<span>${k} <b>${Math.round(v)}</b></span>`)
      .join("")}</div>`;
  }

  function renderMust(d) {
    const p = d.must_read;
    const mount = $("#mustMount");
    if (!p) {
      $("#mustSection").hidden = false;
      mount.innerHTML = `<p class="empty">今天没有一篇够格做精读。</p>`;
      return;
    }
    $("#mustSection").hidden = false;
    const deep = p.deep || {};
    const title = p.title_zh || deep.title_zh || p.title;
    const orig = p.title_zh && p.title ? p.title : "";
    const meta = [
      p.journal,
      p.date,
      p.design_label,
      p.sample_note || (p.sample_n ? `n=${p.sample_n}` : ""),
      p.cited_by ? `被引 ${p.cited_by}` : "",
      p.tier ? `${p.tier} 级期刊` : "",
    ].filter(Boolean);

    const findings = (deep.findings || [])
      .map((f) => `<li><span class="claim">${esc(f.claim)}</span><span class="ev">${esc(f.evidence)}</span></li>`)
      .join("");

    const chart = deep.question
      ? `<dl class="chart">
          <div><dt>主诉 / 问题</dt><dd>${esc(deep.question)}</dd></div>
          <div><dt>检查 / 设计</dt><dd>${esc(deep.design)}${deep.sample_desc ? `<br><span class="muted">${esc(deep.sample_desc)}</span>` : ""}</dd></div>
          <div><dt>诊断 / 证据</dt><dd>${findings ? `<ul class="findings">${findings}</ul>` : ""}${deep.effect ? `<p class="effect"><span>效应量</span>${esc(deep.effect)}</p>` : ""}</dd></div>
          <div><dt>处理 / 与我</dt><dd>${esc(deep.relation)}${deep.transferable ? `<p class="transfer">可迁移：${esc(deep.transferable)}</p>` : ""}</dd></div>
        </dl>`
      : `<p class="fallback-note">这一班没有接模型，所以没有精读卡。下面是摘要原文；接入后会变成「主诉 / 检查 / 诊断 / 处理」四段。</p>
         <p class="fallback">${esc((p.abstract || "").slice(0, 1200))}…</p>`;

    const limits = (deep.limitations || []).length
      ? `<div class="limits"><strong>读到这里要怀疑的地方</strong><ul>${deep.limitations.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>`
      : "";

    const asks = (deep.followups || []).length
      ? `<div class="asks"><h4>读完回答这三个问题</h4><ol>${deep.followups.map((q) => `<li>${esc(q)}</li>`).join("")}</ol></div>`
      : "";

    const glossary = (deep.glossary || []).length
      ? `<p class="glossary">${deep.glossary.map((g) => `<span><b>${esc(g.en)}</b> ${esc(g.cn)}</span>`).join(" ")}</p>`
      : "";

    const pdf = p.pmcid ? `https://europepmc.org/articles/${esc(p.pmcid)}?pdf=render` : "";

    mount.innerHTML = `
      <div class="must-wrap reveal ${store.read.has(p.id) ? "is-read" : ""}" data-id="${esc(p.id)}">
        ${probe(p.design_level, p.design_label || "未标注")}
        <article class="sheet">
          <header class="sheet-head">
            <p class="eyebrow">精读 <span class="tier">${esc(p.tier || "C")} 级</span> ${p.cluster ? `<span class="tier">${esc(p.cluster)}</span>` : ""}</p>
            <h3>${esc(title)}</h3>
            ${orig ? `<p class="orig-title">${esc(orig)}</p>` : ""}
            <div class="meta-line">${meta.map((m) => `<span>${esc(m)}</span>`).join("")}</div>
            ${p.one_line ? `<p class="one-sentence">${esc(p.one_line)}</p>` : ""}
            ${scoreBlock(p.score)}
          </header>
          ${chart}
          ${limits}
          ${asks}
          ${glossary}
          <div class="actions">
            <a class="btn btn-primary" href="${esc(p.url)}" target="_blank" rel="noopener">打开原文</a>
            ${pdf ? `<a class="btn" href="${pdf}" target="_blank" rel="noopener">PDF</a>` : ""}
            <button class="btn" data-act="copy" data-id="${esc(p.id)}" type="button">复制精读笔记</button>
            <button class="btn ${store.read.has(p.id) ? "is-on" : ""}" data-act="read" data-id="${esc(p.id)}" type="button">${store.read.has(p.id) ? "已读" : "标记已读"}</button>
            <button class="btn ${store.saved.has(p.id) ? "is-on" : ""}" data-act="save" data-id="${esc(p.id)}" type="button">${store.saved.has(p.id) ? "已收藏" : "收藏"}</button>
            <button class="btn btn-danger" data-act="dismiss" data-id="${esc(p.id)}" type="button">不感兴趣</button>
          </div>
        </article>
      </div>`;
    mount.dataset.deep = JSON.stringify(deep);
    mount.dataset.raw = JSON.stringify({ id: p.id, title, journal: p.journal, url: p.url });
  }

  function renderScan(d) {
    const list = d.scan || [];
    $("#scanSection").hidden = list.length === 0;
    const mount = $("#scanMount");
    mount.innerHTML = list
      .map((p, i) => {
        const num = String(i + 2).padStart(2, "0");
        const title = p.title_zh || p.title;
        const score = p.score?.final;
        return `
        <article class="scan-item reveal ${store.read.has(p.id) ? "is-read" : ""}" data-id="${esc(p.id)}" style="animation-delay:${80 + i * 60}ms">
          <div class="scan-num">${num}</div>
          <div>
            <h3 class="scan-title"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(title)}</a></h3>
            ${p.one_line ? `<p class="scan-line">${esc(p.one_line)}</p>` : `<p class="scan-line">${esc((p.abstract || "").slice(0, 180))}…</p>`}
            ${p.so_what ? `<p class="scan-so">→ ${esc(p.so_what)}</p>` : ""}
            ${p.caution ? `<p class="scan-caution">要打折扣：${esc(p.caution)}</p>` : ""}
            <div class="scan-tags">
              ${p.cluster ? `<span>${esc(p.cluster)}</span>` : ""}
              <span>${esc(p.journal)}</span>
              <span>${esc(p.design_label)}</span>
              ${p.sample_note ? `<span>${esc(p.sample_note)}</span>` : ""}
              <span>${esc(p.date)}</span>
            </div>
            <details class="abs"><summary>摘要</summary><p>${esc(p.abstract || "")}</p></details>
            <div class="scan-actions">
              <button class="btn btn-sm ${store.read.has(p.id) ? "is-on" : ""}" data-act="read" data-id="${esc(p.id)}" type="button">${store.read.has(p.id) ? "已读" : "标记已读"}</button>
              <button class="btn btn-sm ${store.saved.has(p.id) ? "is-on" : ""}" data-act="save" data-id="${esc(p.id)}" type="button">${store.saved.has(p.id) ? "已收藏" : "收藏"}</button>
              <button class="btn btn-sm btn-danger" data-act="dismiss" data-id="${esc(p.id)}" type="button">不感兴趣</button>
            </div>
          </div>
          <div class="score-chip ${score >= 80 ? "hot" : ""}" title="综合得分">
            ${score != null ? Math.round(score) : "—"}
            <small>分</small>
          </div>
        </article>`;
      })
      .join("");
  }

  function renderWeekly(d) {
    const w = d.weekly;
    $("#weeklySection").hidden = !w;
    if (!w) return;
    const clusters = (w.clusters || [])
      .map((c) => `<li><b>${esc(c.name)} · ${esc(c.n)} 篇</b><span>${esc(c.insight)}</span></li>`)
      .join("");
    const tension = w.tension
      ? `<div class="tension"><p>${esc(w.tension.a)}</p><span class="vs">VS</span><p>${esc(w.tension.b)}</p></div>
         <p class="tension-note">${esc(w.tension.note)}</p>`
      : "";
    const gaps = (w.gaps || []).map((g) => `<li>${esc(g)}</li>`).join("");
    $("#weeklyMount").innerHTML = `
      <article class="weekly reveal">
        <h3>${esc(w.headline || "本周领域地图")}</h3>
        <ul class="clusters">${clusters}</ul>
        ${tension}
        ${w.method_shift ? `<p class="method-shift"><span>方法迁移</span>${esc(w.method_shift)}</p>` : ""}
        ${gaps ? `<p class="gap-title">可以做的空白</p><ul class="gaps">${gaps}</ul>` : ""}
        ${w.next_watch ? `<p class="next-watch">下周盯：${esc(w.next_watch)}</p>` : ""}
      </article>`;
  }

  function renderBacklog(d) {
    const items = d.backlog || [];
    $("#backlogSection").hidden = items.length === 0;
    if (!items.length) return;
    $("#backlogHint").textContent = `${items.length} 篇没读，按等待时间排序`;
    $("#backlogMount").innerHTML = items
      .map(
        (it) => `<div class="backlog-row">
          <span class="backlog-wait">${esc(it.days_waiting || 0)}d</span>
          <div class="backlog-main">
            <a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a>
            <span class="backlog-sub">${esc(it.journal || "")}${it.date_shown ? ` · ${esc(it.date_shown)}` : ""}</span>
          </div>
          <span class="backlog-score">${it.score ? Math.round(it.score) : ""}</span>
        </div>`
      )
      .join("");
  }

  function renderFooter(d) {
    $("#footerMeta").innerHTML = `${esc(d.model || "")} · ${esc(d.generated_at || "")}${d.usage?.calls ? ` · ${d.usage.calls} 次调用` : ""}<br><a href="legacy/index.html">旧版界面</a>`;
  }

  function updateProgress() {
    const papers = shownPapers();
    const total = papers.length;
    const read = papers.filter((p) => store.read.has(p.id)).length;
    $("#progressCount").textContent = `${read} / ${total}`;
    $("#progressBar").style.width = total ? `${(read / total) * 100}%` : "0%";
  }

  function setActiveButtons(id) {
    document.querySelectorAll(`[data-act="read"][data-id="${CSS.escape(id)}"]`).forEach((el) => {
      const on = store.read.has(id);
      el.classList.toggle("is-on", on);
      el.textContent = on ? "已读" : "标记已读";
    });
    document.querySelectorAll(`[data-act="save"][data-id="${CSS.escape(id)}"]`).forEach((el) => {
      const on = store.saved.has(id);
      el.classList.toggle("is-on", on);
      el.textContent = on ? "已收藏" : "收藏";
    });
  }

  function noteText() {
    const d = state.day;
    const p = d.must_read;
    if (!p) return "";
    const deep = p.deep || {};
    const lines = [
      `# ${p.title_zh || p.title}`,
      "",
      `- 期刊：${p.journal}（${p.tier || ""}）｜${p.date}`,
      `- 设计：${p.design_label}｜样本：${p.sample_note || "未提及"}`,
      `- 链接：${p.url}`,
      "",
      `**一句话**：${p.one_line || ""}`,
      "",
      `**问题**：${deep.question || ""}`,
      `**设计**：${deep.design || ""}`,
      `**效应量**：${deep.effect || ""}`,
      `**与我**：${deep.relation || ""}`,
      `**局限**：${(deep.limitations || []).join("；")}`,
      `**可迁移**：${deep.transferable || ""}`,
    ];
    if ((deep.followups || []).length) {
      lines.push("", "**三个追问**", ...deep.followups.map((q) => `- [ ] ${q}`));
    }
    if ((deep.findings || []).length) {
      lines.push("", "**关键证据**", ...deep.findings.map((f) => `- ${f.claim} —— ${f.evidence}`));
    }
    return lines.join("\n");
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      toast("已复制，粘贴到你的笔记里");
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
      toast("已复制");
    }
  }

  let toastTimer;
  function toast(msg) {
    let el = $("#toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "toast";
      el.className = "toast";
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2200);
  }

  function exportFeedback() {
    const d = state.day;
    const ids = shownPapers().map((p) => p.id);
    const payload = {
      date: d.date,
      exported_at: new Date().toISOString(),
      read: ids.filter((id) => store.read.has(id)),
      saved: ids.filter((id) => store.saved.has(id)),
      dismissed: [...store.dismissed],
    };
    if (!payload.read.length && !payload.saved.length && !payload.dismissed.length) {
      toast("今天还没有标记，先读一篇");
      return;
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `feedback-${d.date}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
    toast("已下载。放进 feedback/inbox/ 后生效");
  }

  function bindChrome() {
    $("#aboutBtn").addEventListener("click", () => $("#aboutModal").classList.add("open"));
    $("#closeAbout").addEventListener("click", () => $("#aboutModal").classList.remove("open"));
    $("#aboutModal").addEventListener("click", (e) => {
      if (e.target.id === "aboutModal") $("#aboutModal").classList.remove("open");
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") $("#aboutModal").classList.remove("open");
    });
    $("#feedbackBtn").addEventListener("click", exportFeedback);

    document.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-act]");
      if (!btn) return;
      const id = btn.dataset.id;
      const act = btn.dataset.act;
      if (act === "read") {
        store.read.has(id) ? store.read.delete(id) : store.read.add(id);
      } else if (act === "save") {
        store.saved.has(id) ? store.saved.delete(id) : store.saved.add(id);
      } else if (act === "dismiss") {
        store.dismissed.add(id);
        store.read.delete(id);
        const node = btn.closest(".scan-item, .must-wrap");
        if (node) {
          node.style.transition = "opacity .25s";
          node.style.opacity = "0.35";
        }
        toast("已标记不感兴趣，导出反馈后会永久屏蔽");
      } else if (act === "copy") {
        copyText(noteText());
        return;
      }
      persist();
      setActiveButtons(id);
      document.querySelectorAll(".must-wrap, .scan-item").forEach((n) => {
        n.classList.toggle("is-read", store.read.has(n.dataset.id));
      });
      updateProgress();
    });
  }

  boot();
})();
