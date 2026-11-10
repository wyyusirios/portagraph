/* PortaGraph – общие функции интерфейса и логика экранов. Без сборки и зависимостей. */
"use strict";

const PG = (() => {
  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || "";

  async function api(url, options = {}) {
    const opts = { method: "GET", headers: { Accept: "application/json" }, ...options };
    if (opts.body && typeof opts.body !== "string") {
      opts.body = JSON.stringify(opts.body);
      opts.headers["Content-Type"] = "application/json";
    }
    if (opts.method !== "GET") opts.headers["X-CSRF-Token"] = csrf();
    const res = await fetch(url, opts);
    let data = null;
    try { data = await res.json(); } catch (_) { /* пустой ответ */ }
    if (!res.ok) throw new Error((data && data.error) || `Ошибка ${res.status}`);
    return data;
  }

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const icon = (name, cls = "") => `<svg class="i ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;

  /* Небольшой безопасный Markdown: экранирование, затем **жирный**, `код`, списки, абзацы. */
  function md(text) {
    const inline = (s) => esc(s)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
    const out = [];
    let list = null;
    for (const raw of String(text || "").split("\n")) {
      const line = raw.replace(/\s+$/, "");
      const li = line.match(/^\s*[-•]\s+(.*)$/);
      if (li) { if (!list) { list = []; } list.push(`<li>${inline(li[1])}</li>`); continue; }
      if (list && /^\s{2,}\S/.test(line)) { list[list.length - 1] = list[list.length - 1].replace(/<\/li>$/, `<br>${inline(line.trim())}</li>`); continue; }
      if (list) { out.push(`<ul>${list.join("")}</ul>`); list = null; }
      if (line.trim()) out.push(`<p>${inline(line)}</p>`);
    }
    if (list) out.push(`<ul>${list.join("")}</ul>`);
    return out.join("");
  }

  function toast(message, kind = "success") {
    const box = document.getElementById("flashes");
    const el = document.createElement("div");
    el.className = `flash ${kind}`;
    el.innerHTML = `${icon(kind === "error" ? "alert" : "check")}<div>${esc(message)}</div><button class="x" type="button">${icon("x")}</button>`;
    box.appendChild(el);
    setTimeout(() => el.remove(), 6000);
  }

  const fmt = (n, d = 2) => Number(n).toFixed(d);
  return { api, esc, icon, md, toast, fmt, csrf };
})();

/* ---------------------------------------------------------------- общее */
document.addEventListener("click", (e) => {
  const x = e.target.closest(".flash .x");
  if (x) x.closest(".flash").remove();
  const close = e.target.closest("[data-close]");
  if (close) close.closest("dialog")?.close();
});
setTimeout(() => document.querySelectorAll(".flash").forEach((f) => f.remove()), 7000);
document.addEventListener("submit", (e) => {
  const msg = e.target.getAttribute("data-confirm");
  if (msg && !window.confirm(msg)) e.preventDefault();
});

/* вкладки */
document.querySelectorAll("[data-tabs]").forEach((tabs) => {
  const root = tabs.parentElement;
  tabs.addEventListener("click", (e) => {
    const b = e.target.closest("[data-tab]");
    if (!b) return;
    tabs.querySelectorAll("[data-tab]").forEach((t) => t.classList.toggle("on", t === b));
    root.querySelectorAll("[data-panel]").forEach((p) => p.classList.toggle("hidden", p.dataset.panel !== b.dataset.tab));
  });
});

/* ---------------------------------------------------------------- вход */
document.querySelectorAll(".demo-user").forEach((b) => b.addEventListener("click", () => {
  const f = document.getElementById("login-form");
  f.email.value = b.dataset.email;
  f.password.value = b.dataset.password;
  f.submit();
}));

/* ---------------------------------------------------------------- репозитории: веб-хук */
document.querySelectorAll("[data-webhook]").forEach((b) => b.addEventListener("click", async () => {
  const dlg = document.getElementById("webhook-dialog");
  try {
    const info = await PG.api(b.dataset.webhook);
    dlg.querySelector('[data-f="url"]').value = info.url;
    dlg.querySelector('[data-f="webhook_secret"]').value = info.webhook_secret;
    dlg.querySelector('[data-f="events"]').innerHTML = info.events.length
      ? info.events.map((ev) => `<div class="item"><span class="tag">${PG.esc(ev.event_type)}</span><span class="grow mono">${PG.esc(ev.branch || "")} ${PG.esc((ev.commit_sha || "").slice(0, 8))}</span><span class="faint">${ev.processed ? "анализ №" + ev.run_id : "пропущено"}</span></div>`).join("")
      : '<span class="faint">Событий ещё не было</span>';
    dlg.showModal();
  } catch (err) { PG.toast(err.message, "error"); }
}));

/* ---------------------------------------------------------------- прогресс анализа */
(function runPage() {
  const root = document.getElementById("run");
  if (!root) return;
  const order = ["QUEUED", "FETCHING", "INDEXING", "ANALYZING", "BUILDING_GRAPH", "COMPLETED"];
  const pills = { COMPLETED: "ok", FAILED: "err", CANCELLED: "" };
  const ru = { QUEUED: "В очереди", FETCHING: "Загрузка исходников", INDEXING: "Индексация", ANALYZING: "Анализ", BUILDING_GRAPH: "Построение графа", COMPLETED: "Завершён", FAILED: "Ошибка", CANCELLED: "Отменён" };
  const statLabels = [["repositories", "Репозиториев"], ["files_indexed", "Проиндексировано файлов"], ["files_unchanged", "Без изменений"], ["secrets_redacted", "Скрыто секретов"],
    ["nodes", "Узлов графа"], ["edges", "Связей"], ["cross_repo_links", "Межрепозиторных связей"], ["low_confidence_links", "Связей с уверенностью < 0,7"]];
  let lastLog = -1;
  async function tick() {
    let r;
    try { r = await PG.api(root.dataset.url); } catch (e) { setTimeout(tick, 3000); return; }
    document.getElementById("run-progress").textContent = r.progress + "%";
    document.getElementById("run-bar").style.width = r.progress + "%";
    document.getElementById("run-stage").textContent = r.stage_message || "";
    const cls = pills[r.status] ?? "accent live";
    document.getElementById("run-pill").innerHTML = `<span class="pill sm ${cls}"><span class="dot"></span>${ru[r.status] || r.status}</span>`;
    const idx = order.indexOf(r.status);
    root.querySelectorAll(".step").forEach((s) => {
      const i = order.indexOf(s.dataset.s);
      s.classList.toggle("done", r.status === "COMPLETED" || (idx > -1 && i < idx));
      s.classList.toggle("now", r.status !== "COMPLETED" && i === idx);
    });
    if (r.log.length !== lastLog) {
      lastLog = r.log.length;
      const box = document.getElementById("run-log");
      box.innerHTML = r.log.map((l) => `<div class="${l.level}"><span class="t">${PG.esc(l.t)}</span><span>${PG.esc(l.text)}</span></div>`).join("") || '<div class="faint">Ожидание…</div>';
      box.scrollTop = box.scrollHeight;
    }
    if (r.stats && Object.keys(r.stats).length) {
      document.getElementById("run-stats").innerHTML = statLabels.filter(([k]) => r.stats[k] !== undefined)
        .map(([k, t]) => `<div class="card stat"><span class="label">${t}</span><span class="value">${r.stats[k]}</span></div>`).join("");
      document.getElementById("run-time").textContent = r.stats.duration_sec !== undefined ? `${r.stats.duration_sec} с` : "";
    }
    const done = ["COMPLETED", "FAILED", "CANCELLED"].includes(r.status);
    document.getElementById("cancel-form")?.classList.toggle("hidden", done);
    document.getElementById("open-map").classList.toggle("hidden", r.status !== "COMPLETED");
    const err = document.getElementById("run-error");
    err.classList.toggle("hidden", !r.error_message);
    err.querySelector("div").textContent = r.error_message || "";
    if (!done) setTimeout(tick, 900);
  }
  tick();
})();

/* ---------------------------------------------------------------- просмотр кода: выделение строк */
(function codePage() {
  const code = document.getElementById("code");
  if (!code) return;
  const m = (code.dataset.sel || "").match(/^(\d+)-(\d+)$/);
  if (m) {
    const [a, b] = [+m[1], +m[2]];
    for (let i = a; i <= b; i++) document.getElementById("L-" + i)?.classList.add("sel");
    const first = document.getElementById("L-" + Math.max(1, a - 4));
    if (first) setTimeout(() => first.scrollIntoView({ block: "start" }), 50);
  }
  code.addEventListener("click", (e) => {
    const line = e.target.closest('span[id^="L-"]');
    if (!line || e.offsetX > 60 || e.target !== line) return;
    const n = line.id.slice(2);
    history.replaceState(null, "", `?l=${n}`);
    code.querySelectorAll(".sel").forEach((s) => s.classList.remove("sel"));
    line.classList.add("sel");
  });
})();

/* ---------------------------------------------------------------- ассистент */
(function assistantPage() {
  const chat = document.getElementById("chat");
  if (!chat) return;
  const scroll = document.getElementById("chat-scroll");
  const form = document.getElementById("ask-form");
  const q = document.getElementById("question");
  let sid = chat.dataset.sid || null;
  const fileUrl = (c) => `${chat.dataset.files.replace(/\/code$/, "")}/files/${c.file_id}?l=${c.start_line}-${c.end_line}`;

  function render(el, m) {
    const isUser = m.role === "USER";
    el.className = `msg ${isUser ? "user" : "bot"}`;
    const cites = (m.citations || []).map((c) =>
      `<a class="cite" href="${fileUrl(c)}" title="${PG.esc(c.label || "")}">${PG.esc(c.path)}:${c.start_line}${c.end_line > c.start_line ? "–" + c.end_line : ""}</a>`).join("");
    const conf = m.confidence != null ? `<span class="pill sm ${m.confidence < 0.4 ? "warn" : m.confidence >= 0.7 ? "ok" : ""}">уверенность ${PG.fmt(m.confidence)}</span>` : "";
    el.innerHTML = `<div class="who">${isUser ? PG.esc((document.querySelector(".user-chip .avatar")?.textContent || "Я").trim()) : "PG"}</div>
      <div class="body">${isUser ? `<div class="bubble">${PG.esc(m.content)}</div>` : `<div class="text">${PG.md(m.content)}</div>
      ${cites ? `<div><div class="faint small" style="margin-bottom:6px">Источники</div><div class="cites">${cites}</div></div>` : ""}
      <div class="row wrap">${conf}<span class="faint small">Демо-режим: граф + полнотекстовый поиск</span></div>`}</div>`;
  }
  scroll.querySelectorAll("[data-msg]").forEach((el) => render(el, JSON.parse(el.dataset.msg)));
  scroll.scrollTop = scroll.scrollHeight;

  function add(m) {
    document.getElementById("chat-empty")?.remove();
    document.getElementById("suggest")?.remove();
    const el = document.createElement("div");
    render(el, m);
    scroll.appendChild(el);
    scroll.scrollTop = scroll.scrollHeight;
    return el;
  }

  async function ask(text) {
    text = text.trim();
    if (!text) return;
    add({ role: "USER", content: text });
    const wait = document.createElement("div");
    wait.className = "msg bot";
    wait.innerHTML = '<div class="who">PG</div><div class="body"><div class="typing"><span></span><span></span><span></span></div></div>';
    scroll.appendChild(wait);
    scroll.scrollTop = scroll.scrollHeight;
    form.querySelector("button").disabled = true;
    try {
      const m = await PG.api(chat.dataset.url, { method: "POST", body: { session_id: sid ? +sid : null, question: text } });
      wait.remove();
      add(m);
      if (!sid) {
        sid = m.session_id;
        history.replaceState(null, "", `${chat.dataset.base}/${sid}`);
        const list = document.querySelector(".chat-list");
        list.querySelector("p.faint")?.remove();
        const a = document.createElement("a");
        a.className = "s ellipsis on"; a.href = `${chat.dataset.base}/${sid}`; a.textContent = text; a.title = text;
        list.querySelector(".nav-label").after(a);
      }
    } catch (err) {
      wait.remove();
      PG.toast(err.message, "error");
    } finally { form.querySelector("button").disabled = false; q.focus(); }
  }

  if (form) {
    form.addEventListener("submit", (e) => { e.preventDefault(); const t = q.value; q.value = ""; q.style.height = ""; ask(t); });
    q.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
    q.addEventListener("input", () => { q.style.height = "auto"; q.style.height = Math.min(200, q.scrollHeight) + "px"; });
    document.getElementById("suggest")?.addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) ask(b.textContent); });
    q.focus();
  }
})();

/* ---------------------------------------------------------------- impact analysis: выбор узлов */
(function impactPage() {
  const form = document.getElementById("impact-form");
  if (!form) return;
  const input = document.getElementById("picker-input");
  const box = document.getElementById("picker-results");
  const chosenEl = document.getElementById("chosen");
  const depth = document.getElementById("depth");
  const chosen = new Map();
  const typeRu = { SERVICE: "Сервис", REPOSITORY: "Репозиторий", DATABASE: "База данных", MESSAGE_QUEUE: "Топик", EXTERNAL_SYSTEM: "Внешняя система", CLASS: "Класс", ENTITY: "Сущность", FUNCTION: "Функция" };
  const draw = () => {
    chosenEl.innerHTML = [...chosen.values()].map((n) =>
      `<span class="pill accent">${PG.esc(n.name)}<span class="faint small">${typeRu[n.type] || ""}</span><button type="button" data-rm="${n.id}" aria-label="Убрать">${PG.icon("x")}</button></span>`).join("")
      || '<span class="faint small">Компоненты не выбраны</span>';
  };
  const pre = JSON.parse(chosenEl.dataset.pre || "null");
  if (pre) chosen.set(pre.id, pre);
  draw();
  depth.addEventListener("input", () => { document.getElementById("depth-val").textContent = depth.value; });
  chosenEl.addEventListener("click", (e) => { const b = e.target.closest("[data-rm]"); if (b) { chosen.delete(+b.dataset.rm); draw(); } });
  let timer;
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const v = input.value.trim();
      if (!v) { box.classList.add("hidden"); return; }
      try {
        const rows = await PG.api(`${form.dataset.search}?q=${encodeURIComponent(v)}`);
        box.innerHTML = rows.map((r) => `<button type="button" data-id="${r.id}" data-name="${PG.esc(r.name)}" data-type="${r.type}"><span class="grow ellipsis">${PG.esc(r.name)}</span><span class="tag">${typeRu[r.type] || r.type}</span>${r.repo_name && r.repo_name !== r.name ? `<span class="faint small">${PG.esc(r.repo_name)}</span>` : ""}</button>`).join("")
          || '<div class="faint small" style="padding:8px">Ничего не найдено</div>';
        box.classList.remove("hidden");
      } catch (err) { PG.toast(err.message, "error"); }
    }, 180);
  });
  box.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-id]");
    if (!b) return;
    chosen.set(+b.dataset.id, { id: +b.dataset.id, name: b.dataset.name, type: b.dataset.type });
    draw();
    input.value = "";
    box.classList.add("hidden");
    input.focus();
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".picker")) box.classList.add("hidden"); });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!chosen.size) { PG.toast("Выберите хотя бы один компонент", "error"); return; }
    const status = document.getElementById("impact-status");
    status.textContent = "Считаю…";
    try {
      const r = await PG.api(form.dataset.url, { method: "POST", body: { node_ids: [...chosen.keys()], depth: +depth.value, description: document.getElementById("impact-desc").value } });
      location.href = `${form.dataset.report}/${r.id}#report`;
    } catch (err) { status.textContent = ""; PG.toast(err.message, "error"); }
  });
})();

/* свернуть / раскрыть длинные списки (обзор проекта) */
document.querySelectorAll("[data-expand]").forEach((b) => b.addEventListener("click", () => {
  const card = b.closest("[data-collapsible]");
  const open = !b.classList.contains("open");
  card.querySelectorAll(".extra").forEach((r) => r.classList.toggle("hidden", !open));
  b.classList.toggle("open", open);
  b.querySelector("span").textContent = open ? b.dataset.less : b.dataset.more;
}));
