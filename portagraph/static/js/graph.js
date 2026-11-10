/* PortaGraph — рендерер графа архитектуры на SVG.
   Раскладка послойная (слева направо по направлению зависимости «A → B: A зависит от B»),
   порядок внутри слоя — эвристика барицентров. Панорама, масштаб, выбор узла, подсветка соседей,
   пунктир для связей с уверенностью ниже 0,7, анимация асинхронных связей. */
"use strict";

const PGGraph = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const ASYNC = new Set(["PUBLISHES", "CONSUMES"]);
  const EDGE_RU = { CALLS_HTTP: "HTTP", PUBLISHES: "публикует", CONSUMES: "читает", READS_WRITES: "данные", DEPENDS_ON: "зависимость", IMPORTS: "использует" };
  const COLORS = { SERVICE: "#e0913f", FRONTEND: "#6fa8dc", MESSAGE_QUEUE: "#a99cf0", DATABASE: "#7fb069", EXTERNAL_SYSTEM: "#c4623a",
    REPOSITORY: "#b5b5b0", CLASS: "#e0913f", ENTITY: "#7fb069", FUNCTION: "#6fa8dc", MODULE: "#b5b5b0" };

  const el = (tag, attrs = {}, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) if (v !== undefined && v !== null) e.setAttribute(k, v);
    if (parent) parent.appendChild(e);
    return e;
  };
  const colorOf = (n) => (n.type === "SERVICE" && n.role === "FRONTEND" ? COLORS.FRONTEND : COLORS[n.type] || "#b5b5b0");
  const subtitle = (n, mode) => {
    if (mode === "detailed") return n.stereotype ? `@${n.stereotype}` : (n.group || n.type_ru);
    if (n.type === "SERVICE") return [n.role === "FRONTEND" ? "Фронтенд" : "Сервис", (n.stack || []).filter((s) => s !== "Docker")[0]].filter(Boolean).join(" · ");
    if (n.type === "MESSAGE_QUEUE") return `Топик${n.broker ? " · " + n.broker : ""}`;
    if (n.type === "DATABASE") return n.engine || "База данных";
    if (n.type === "REPOSITORY") return "Библиотека";
    return n.type_ru;
  };
  const trim = (s, n) => (s.length > n ? s.slice(0, n - 1) + "…" : s);

  /* ---------- послойная раскладка */
  function layout(nodes, edges, opt) {
    const ids = nodes.map((n) => n.id);
    const out = new Map(ids.map((i) => [i, []]));
    const inc = new Map(ids.map((i) => [i, []]));
    for (const e of edges) { if (out.has(e.source) && out.has(e.target)) { out.get(e.source).push(e.target); inc.get(e.target).push(e.source); } }
    // удаляем циклы (DFS), чтобы слои были определены
    const state = new Map(), back = new Set();
    const dfs = (v) => {
      state.set(v, 1);
      for (const w of out.get(v)) {
        if (state.get(w) === 1) back.add(v + ">" + w);
        else if (!state.get(w)) dfs(w);
      }
      state.set(v, 2);
    };
    ids.slice().sort((a, b) => inc.get(a).length - inc.get(b).length).forEach((v) => { if (!state.get(v)) dfs(v); });
    const layer = new Map();
    const lay = (v, guard = 0) => {
      if (layer.has(v)) return layer.get(v);
      if (guard > ids.length) return 0;
      const preds = inc.get(v).filter((u) => !back.has(u + ">" + v));
      const l = preds.length ? Math.max(...preds.map((u) => lay(u, guard + 1) + 1)) : 0;
      layer.set(v, l);
      return l;
    };
    ids.forEach((v) => lay(v));
    // изолированные узлы-хранилища уводим вправо, источники без связей — влево
    const maxL = Math.max(0, ...layer.values());
    for (const n of nodes) {
      if (opt.sinkRight && ["DATABASE", "MESSAGE_QUEUE", "EXTERNAL_SYSTEM"].includes(n.type) && !out.get(n.id).length) {
        layer.set(n.id, Math.max(layer.get(n.id), inc.get(n.id).length ? Math.max(...inc.get(n.id).map((u) => layer.get(u) + 1)) : maxL));
      }
    }
    const layers = [];
    for (const n of nodes) (layers[layer.get(n.id)] ||= []).push(n.id);
    for (let i = 0; i < layers.length; i++) layers[i] ||= [];
    const pos = new Map();
    layers.forEach((L) => L.sort((a, b) => String(nodes.find((n) => n.id === a).label).localeCompare(nodes.find((n) => n.id === b).label)));
    const order = () => layers.forEach((L) => L.forEach((v, i) => pos.set(v, i)));
    order();
    for (let iter = 0; iter < 8; iter++) {
      const down = iter % 2 === 0;
      const seq = down ? layers.slice(1) : layers.slice(0, -1).reverse();
      for (const L of seq) {
        const bc = new Map(L.map((v) => {
          const nb = down ? inc.get(v) : out.get(v);
          const ps = nb.filter((u) => pos.has(u) && layer.get(u) !== layer.get(v)).map((u) => pos.get(u));
          return [v, ps.length ? ps.reduce((a, b) => a + b, 0) / ps.length : pos.get(v)];
        }));
        L.sort((a, b) => bc.get(a) - bc.get(b));
        L.forEach((v, i) => pos.set(v, i));
      }
    }
    return layers;
  }

  /* координаты: слева направо (LR) или сверху вниз (TB) — выбирается то, что крупнее помещается в холст */
  function place(layers, size, W, H) {
    const tallest = Math.max(1, ...layers.map((L) => L.length));
    const lr = { w: layers.length * (size.w + size.gx) - size.gx, h: tallest * (size.h + size.gy) - size.gy };
    const tbGap = { gx: 20, gy: 58 };
    const tb = { w: tallest * (size.w + tbGap.gx) - tbGap.gx, h: layers.length * (size.h + tbGap.gy) - tbGap.gy };
    const k = (b) => Math.min(W / (b.w + 120), H / (b.h + 120));
    const dir = k(tb) > k(lr) * 1.08 ? "TB" : "LR";
    const xy = new Map();
    layers.forEach((L, li) => {
      if (dir === "LR") {
        const off = ((tallest - L.length) * (size.h + size.gy)) / 2;
        L.forEach((v, i) => xy.set(v, { x: li * (size.w + size.gx), y: off + i * (size.h + size.gy) }));
      } else {
        const off = ((tallest - L.length) * (size.w + tbGap.gx)) / 2;
        L.forEach((v, i) => xy.set(v, { x: off + i * (size.w + tbGap.gx), y: li * (size.h + tbGap.gy) }));
      }
    });
    return { xy, dir };
  }

  /* ---------- холст: панорама и масштаб */
  function viewport(svg) {
    const vb = { x: 0, y: 0, w: 1000, h: 700 };
    const apply = () => svg.setAttribute("viewBox", `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
    let drag = null, moved = false;
    svg.addEventListener("pointerdown", (e) => {
      if (e.target.closest(".g-node")) return;
      drag = { x: e.clientX, y: e.clientY, vx: vb.x, vy: vb.y }; moved = false;
      svg.classList.add("dragging"); svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const k = vb.w / svg.clientWidth;
      if (Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) > 3) moved = true;
      vb.x = drag.vx - (e.clientX - drag.x) * k; vb.y = drag.vy - (e.clientY - drag.y) * k; apply();
    });
    const end = () => { drag = null; svg.classList.remove("dragging"); };
    svg.addEventListener("pointerup", end); svg.addEventListener("pointercancel", end);
    const zoom = (f, cx, cy) => {
      const nw = Math.min(8000, Math.max(200, vb.w * f));
      const r = nw / vb.w;
      vb.x = cx - (cx - vb.x) * r; vb.y = cy - (cy - vb.y) * r; vb.w = nw; vb.h *= r; apply();
    };
    svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = svg.getBoundingClientRect();
      const cx = vb.x + ((e.clientX - rect.left) / rect.width) * vb.w;
      const cy = vb.y + ((e.clientY - rect.top) / rect.height) * vb.h;
      zoom(e.deltaY > 0 ? 1.12 : 1 / 1.12, cx, cy);
    }, { passive: false });
    return {
      fit(box, pad = 60) {
        const W = svg.clientWidth || 1000, H = svg.clientHeight || 700;
        const bw = box.w + pad * 2, bh = box.h + pad * 2;
        const s = Math.max(bw / W, bh / H, 0.75);
        vb.w = W * s; vb.h = H * s; vb.x = box.x - pad - (vb.w - bw) / 2; vb.y = box.y - pad - (vb.h - bh) / 2; apply();
      },
      center(x, y) { vb.x = x - vb.w / 2; vb.y = y - vb.h / 2; apply(); },
      zoomBy(f) { zoom(f, vb.x + vb.w / 2, vb.y + vb.h / 2); },
      wasDrag: () => moved,
    };
  }

  /* ---------- отрисовка */
  function draw(svg, data, opt) {
    svg.innerHTML = "";
    const mode = opt.mode;
    const size = mode === "detailed" ? { w: 184, h: 44, gx: 70, gy: 16 } : { w: 178, h: 52, gx: 76, gy: 24 };
    const layers = layout(data.nodes, data.edges, { sinkRight: mode !== "detailed" });
    const { xy, dir } = place(layers, size, svg.clientWidth || 1000, svg.clientHeight || 700);
    const defs = el("defs", {}, svg);
    for (const [id, c] of [["arr", "#6a6a63"], ["arr-hl", "#e0913f"], ["arr-async", "#8f7cd6"], ["arr-ok", "#7fb069"]]) {
      const m = el("marker", { id, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: "auto-start-reverse" }, defs);
      el("path", { d: "M0,0 L10,5 L0,10 z", fill: c }, m);
    }
    const root = el("g", {}, svg);
    const gEdges = el("g", {}, root), gLabels = el("g", {}, root), gNodes = el("g", {}, root);
    const nodeEls = new Map(), edgeEls = [];
    for (const e of data.edges) {
      const a = xy.get(e.source), b = xy.get(e.target);
      if (!a || !b) continue;
      let d;
      if (dir === "LR") {
        const sx = a.x + size.w, sy = a.y + size.h / 2, tx = b.x, ty = b.y + size.h / 2;
        if (tx > sx + 10) {
          const dx = Math.max(40, (tx - sx) / 2);
          d = `M${sx},${sy} C${sx + dx},${sy} ${tx - dx},${ty} ${tx},${ty}`;
        } else { // обратная или внутрислойная связь — дугой снизу
          const low = Math.max(a.y, b.y) + size.h + 40;
          d = `M${a.x + size.w / 2},${a.y + size.h} C${a.x + size.w / 2},${low} ${b.x + size.w / 2},${low} ${b.x + size.w / 2},${b.y + size.h}`;
        }
      } else {
        const sx = a.x + size.w / 2, sy = a.y + size.h, tx = b.x + size.w / 2, ty = b.y;
        if (ty > sy + 10) {
          const dy = Math.max(30, (ty - sy) / 2);
          d = `M${sx},${sy} C${sx},${sy + dy} ${tx},${ty - dy} ${tx},${ty}`;
        } else { // обратная связь — дугой справа
          const right = Math.max(a.x, b.x) + size.w + 50;
          d = `M${a.x + size.w},${a.y + size.h / 2} C${right},${a.y + size.h / 2} ${right},${b.y + size.h / 2} ${b.x + size.w},${b.y + size.h / 2}`;
        }
      }
      const cls = ["g-edge"];
      if (ASYNC.has(e.type)) cls.push("async");
      if (e.type === "IMPORTS") cls.push("code");
      if (e.verified) cls.push("verified");
      else if (e.confidence < 0.7) cls.push("low");
      const p = el("path", { d, class: cls.join(" "), "marker-end": `url(#${ASYNC.has(e.type) ? "arr-async" : e.verified ? "arr-ok" : "arr"})` }, gEdges);
      const t = el("title", {}, p);
      t.textContent = `${EDGE_RU[e.type] || e.type}${e.label ? " · " + e.label : ""} · уверенность ${Number(e.confidence).toFixed(2)}${e.verified ? " · подтверждено" : ""}`;
      edgeEls.push({ e, p });
    }
    for (const n of data.nodes) {
      const { x, y } = xy.get(n.id);
      const g = el("g", { class: "g-node" + (n.external ? " ext" : ""), transform: `translate(${x},${y})`, tabindex: 0 }, gNodes);
      el("rect", { class: "bg", width: size.w, height: size.h, rx: 10 }, g);
      el("rect", { class: "chip", x: 12, y: size.h / 2 - 7, width: 14, height: 14, rx: n.type === "DATABASE" ? 7 : n.type === "MESSAGE_QUEUE" ? 2 : 4, fill: colorOf(n) }, g);
      const tt = el("text", { class: "t", x: 36, y: size.h / 2 - (mode === "detailed" ? 2 : 3) }, g);
      tt.textContent = trim(n.label, mode === "detailed" ? 22 : 21);
      const st = el("text", { class: "s", x: 36, y: size.h / 2 + 13 }, g);
      st.textContent = trim(subtitle(n, mode) || "", 28);
      if (n.verified) { const v = el("circle", { cx: size.w - 14, cy: 14, r: 4, fill: "#7fb069" }, g); el("title", {}, v).textContent = "Подтверждено архитектором"; }
      else if (n.confidence != null && n.confidence < 0.7) { const v = el("circle", { cx: size.w - 14, cy: 14, r: 4, fill: "#e0b23f" }, g); el("title", {}, v).textContent = `Уверенность ${Number(n.confidence).toFixed(2)}`; }
      el("title", {}, g).textContent = `${n.label}\n${n.type_ru}${n.description ? "\n" + n.description : ""}`;
      nodeEls.set(n.id, g);
    }
    let bx = Infinity, by = Infinity, bx2 = -Infinity, by2 = -Infinity;
    for (const { x, y } of xy.values()) { bx = Math.min(bx, x); by = Math.min(by, y); bx2 = Math.max(bx2, x + size.w); by2 = Math.max(by2, y + size.h + 40); }
    return { nodeEls, edgeEls, xy, size, box: { x: bx, y: by, w: bx2 - bx, h: by2 - by }, gLabels };
  }

  /* ---------- подсветка */
  function highlight(r, id) {
    const near = new Set([id]);
    for (const { e, p } of r.edgeEls) {
      const on = e.source === id || e.target === id;
      if (on) { near.add(e.source); near.add(e.target); }
      p.classList.toggle("hl", on);
      p.classList.toggle("dim", id != null && !on);
      p.setAttribute("marker-end", `url(#${on ? "arr-hl" : ASYNC.has(e.type) ? "arr-async" : e.verified ? "arr-ok" : "arr"})`);
    }
    r.gLabels.innerHTML = "";
    for (const [nid, g] of r.nodeEls) {
      g.classList.toggle("sel", nid === id);
      g.classList.toggle("dim", id != null && !near.has(nid));
    }
    if (id == null) return;
    for (const { e } of r.edgeEls) {
      if (e.source !== id && e.target !== id) continue;
      const a = r.xy.get(e.source), b = r.xy.get(e.target);
      const t = el("text", { class: "g-label", x: (a.x + b.x) / 2 + r.size.w / 2, y: (a.y + b.y) / 2 + r.size.h / 2 - 6, "text-anchor": "middle" }, r.gLabels);
      t.textContent = `${EDGE_RU[e.type] || e.type} · ${Number(e.confidence).toFixed(2)}`;
    }
  }

  return { draw, viewport, highlight, colorOf, EDGE_RU };
})();

/* ================================================================ экраны карты и графа кода */
(function workspace() {
  const ws = document.getElementById("ws");
  if (!ws) return;
  const pid = ws.dataset.pid, mode = ws.dataset.mode;
  const svg = document.getElementById("graph");
  const vp = PGGraph.viewport(svg);
  const panelEmpty = document.getElementById("panel-empty");
  const panelNode = document.getElementById("panel-node");
  const canVerify = ws.dataset.canVerify === "1", canImpact = ws.dataset.canImpact === "1";
  const base = `/p/${pid}`;
  let data = null, view = null, selected = null, rendered = null;

  const filters = () => ({
    low: document.getElementById("show-low")?.checked ?? true,
    code: document.getElementById("show-code")?.checked ?? true,
    ext: document.getElementById("show-ext")?.checked ?? true,
  });

  function visible() {
    const f = filters();
    let nodes = data.nodes, edges = data.edges;
    if (!f.ext) { const keep = new Set(nodes.filter((n) => !n.external).map((n) => n.id)); nodes = nodes.filter((n) => keep.has(n.id)); edges = edges.filter((e) => keep.has(e.source) && keep.has(e.target)); }
    if (!f.low) edges = edges.filter((e) => e.verified || e.confidence >= 0.7);
    if (!f.code) edges = edges.filter((e) => e.type !== "IMPORTS");
    return { nodes, edges };
  }

  function render(keepView) {
    const v = visible();
    rendered = PGGraph.draw(svg, v, { mode });
    rendered.nodeEls.forEach((g, id) => {
      g.addEventListener("click", (ev) => { ev.stopPropagation(); select(id); });
      g.addEventListener("dblclick", (ev) => { ev.stopPropagation(); open(id); });
      g.addEventListener("keydown", (ev) => { if (ev.key === "Enter") select(id); });
    });
    if (!keepView) vp.fit(rendered.box);
    if (selected && rendered.nodeEls.has(selected)) PGGraph.highlight(rendered, selected);
  }

  function open(id) {
    const n = data.nodes.find((x) => x.id === id);
    if (!n) return;
    if (mode === "overview" && (n.type === "SERVICE" || n.type === "REPOSITORY") && n.repo_id) location.href = `${base}/graph?repo=${n.repo_id}`;
    if (mode === "detailed") location.href = `${base}/graph?focus=${id}`;
  }

  svg.addEventListener("click", () => { if (!vp.wasDrag()) { selected = null; PGGraph.highlight(rendered, null); showEmpty(); } });
  const showEmpty = () => { ws.classList.add("no-panel"); panelEmpty.classList.remove("hidden"); panelNode.classList.add("hidden"); panelNode.innerHTML = ""; };

  async function load() {
    const params = new URLSearchParams();
    if (mode === "detailed") {
      if (ws.dataset.repo) params.set("repo", ws.dataset.repo);
      if (ws.dataset.focus) params.set("focus", ws.dataset.focus);
    }
    try {
      data = await PG.api(`/api/projects/${pid}/graph/${mode}?${params}`);
    } catch (err) { PG.toast(err.message, "error"); return; }
    if (mode === "detailed") {
      const sel = document.getElementById("repo-select");
      if (data.repository_id && sel) sel.value = data.repository_id;
      if (data.focus) {
        const f = data.nodes.find((n) => n.id === data.focus);
        document.getElementById("focus-chip").classList.remove("hidden");
        document.getElementById("focus-name").textContent = `Окрестность: ${f ? f.label : data.focus}`;
      }
      if (!data.nodes.length) { ws.classList.remove("no-panel"); svg.innerHTML = ""; panelEmpty.querySelector("h3").textContent = "В этом репозитории нет классов"; panelEmpty.querySelector("p").textContent = "Выберите другой репозиторий: у инфраструктуры и документации графа кода нет."; return; }
    }
    render(false);
    const focus = +ws.dataset.focus || (mode === "overview" ? +new URLSearchParams(location.search).get("node") : 0);
    if (focus && rendered.nodeEls.has(focus)) select(focus, true);
    else if (mode === "overview" && focus) select(focus, false, true);
  }

  async function select(id, center, panelOnly) {
    selected = id;
    if (!panelOnly) PGGraph.highlight(rendered, id);
    if (center && rendered.xy.get(id)) { const p = rendered.xy.get(id); vp.center(p.x + rendered.size.w / 2, p.y + rendered.size.h / 2); }
    try {
      const d = await PG.api(`/api/projects/${pid}/nodes/${id}`);
      if (selected !== id) return;
      panel(d);
    } catch (err) { PG.toast(err.message, "error"); }
  }

  function evLinks(d, list) {
    return (list || []).slice(0, 4).map((ev) => {
      const fid = d.file_ids[`${ev.repo}/${ev.path}`];
      const label = `${ev.repo}/${ev.path}:${ev.line || 1}`;
      return `<span>${PG.esc(ev.rule || "")}${ev.snippet ? ": <code>" + PG.esc(ev.snippet.slice(0, 80)) + "</code>" : ""}</span>` +
        (fid ? `<a href="${base}/files/${fid}?l=${ev.line || 1}">${PG.esc(label)}</a>` : `<span class="mono">${PG.esc(label)}</span>`);
    }).join("");
  }

  function rel(d, r, dir) {
    const conf = r.verified ? `<span class="pill sm ok">${PG.icon("check")} подтверждено</span>`
      : r.rejected ? '<span class="pill sm err">отклонено</span>'
      : `<span class="conf ${r.confidence < 0.7 ? "low" : ""}"><span class="bar"><i style="width:${Math.round(r.confidence * 100)}%"></i></span>${PG.fmt(r.confidence)}</span>`;
    const what = PGGraph.EDGE_RU[r.type] || r.type;
    const acts = canVerify && r.type !== "CONTAINS" ? `<div class="acts">${!r.verified ? `<button class="btn sm" data-verify="${r.id}" data-d="CONFIRM">${PG.icon("check")}Подтвердить</button>` : ""}${!r.rejected ? `<button class="btn sm ghost danger" data-verify="${r.id}" data-d="REJECT">${PG.icon("x")}Отклонить</button>` : ""}</div>` : "";
    return `<div class="r ${r.rejected ? "rejected" : ""}"><div class="top"><span class="tag">${PG.esc(what)}</span>
      <a class="grow ellipsis" href="#" data-goto="${r.node_id}" style="font-weight:500">${dir === "out" ? "→ " : "← "}${PG.esc(r.name)}</a>${conf}</div>
      ${r.evidence && r.evidence.length ? `<div class="ev">${evLinks(d, r.evidence)}</div>` : ""}${acts}</div>`;
  }

  function panel(d) {
    ws.classList.remove("no-panel");
    panelEmpty.classList.add("hidden");
    panelNode.classList.remove("hidden");
    const m = d.metadata || {};
    const outs = d.outgoing.filter((r) => r.type !== "CONTAINS"), ins = d.incoming.filter((r) => r.type !== "CONTAINS");
    const eps = (m.endpoints || []).slice(0, 30);
    const color = PGGraph.colorOf({ type: d.type, role: m.role });
    const fileLink = d.source_file_id ? `${base}/files/${d.source_file_id}?l=${d.start_line || 1}-${d.end_line || d.start_line || 1}` : null;
    const conf = d.verified ? `<span class="pill sm ok">${PG.icon("check")} подтверждено архитектором</span>`
      : `<span class="conf ${d.confidence < 0.7 ? "low" : ""}" title="Уверенность вывода"><span class="bar"><i style="width:${Math.round(d.confidence * 100)}%"></i></span>${PG.fmt(d.confidence)}</span>`;
    panelNode.innerHTML = `
      <div class="panel-head" style="position:relative">
        <button class="btn sm ghost icon panel-close" type="button" data-close-panel title="Закрыть">${PG.icon("x")}</button>
        <div class="row" style="padding-right:36px"><span class="pill sm" style="--c:${hexRgb(color)}">${PG.esc(d.type_ru)}</span>${conf}</div>
        <h2 style="font-size:18px;overflow-wrap:anywhere">${PG.esc(d.name)}</h2>
        ${d.repo_name ? `<div class="faint small">${PG.esc(d.repo_name)}${d.file_path ? " · " + PG.esc(d.file_path) : ""}</div>` : ""}
        <div class="row wrap">
          ${fileLink ? `<a class="btn sm" href="${fileLink}">${PG.icon("code")}Код</a>` : ""}
          ${["SERVICE", "REPOSITORY"].includes(d.type) && mode === "overview" ? `<a class="btn sm" href="${base}/graph?repo=${repoIdOf(d)}">${PG.icon("graph")}Граф кода</a>` : ""}
          ${["CLASS", "ENTITY", "FUNCTION"].includes(d.type) && mode === "detailed" ? `<a class="btn sm" href="${base}/graph?focus=${d.id}">${PG.icon("graph")}Окрестность</a>` : ""}
          ${canImpact ? `<a class="btn sm" href="${base}/impact?node=${d.id}">${PG.icon("zap")}Impact</a>` : ""}
          ${canVerify && !d.verified ? `<button class="btn sm" data-verify-node="${d.id}">${PG.icon("check")}Подтвердить</button>` : ""}
        </div>
      </div>
      <div class="panel-body">
        <div><h4>Назначение</h4><p class="${d.description ? "" : "faint"}" style="line-height:1.6">${PG.esc(d.description || "Описание не определено")}</p></div>
        ${m.stack && m.stack.length ? `<div><h4>Стек</h4><div class="row wrap">${m.stack.map((s) => `<span class="tag">${PG.esc(s)}</span>`).join("")}</div></div>` : ""}
        ${m.reasons && m.reasons.length ? `<div><h4>Почему такая роль</h4><ul class="muted small" style="margin:0;padding-left:18px">${m.reasons.slice(0, 5).map((r) => `<li>${PG.esc(r)}</li>`).join("")}</ul></div>` : ""}
        ${m.table ? `<div><h4>Таблица</h4><code>${PG.esc(m.table)}</code></div>` : ""}
        ${eps.length ? `<div><h4>API · ${(m.endpoints || []).length}</h4><div class="side-list">${eps.map((ep) => `<span class="row small" style="padding:3px 0"><span class="tag">${PG.esc(ep.method || "")}</span><code class="ellipsis">${PG.esc(ep.path || "")}</code></span>`).join("")}</div></div>` : ""}
        <div><h4>Зависит от · ${outs.length}</h4><div class="rel">${outs.map((r) => rel(d, r, "out")).join("") || '<span class="faint small">Нет исходящих связей</span>'}</div></div>
        <div><h4>Зависят от него · ${ins.length}</h4><div class="rel">${ins.map((r) => rel(d, r, "in")).join("") || '<span class="faint small">Нет входящих связей</span>'}</div></div>
        ${d.children && d.children.length && mode === "overview" ? `<div><h4>Содержит · ${d.children.length}</h4><div class="side-list">${d.children.slice(0, 40).map((c) => `<a href="${base}/graph?focus=${c.id}">${PG.esc(c.name)}<span class="faint small" style="margin-left:auto">${PG.esc(c.type)}</span></a>`).join("")}</div></div>` : ""}
        <div class="faint small mono" style="overflow-wrap:anywhere">${PG.esc(d.qualified_name)}</div>
      </div>`;
  }
  const hexRgb = (h) => { const n = parseInt(h.slice(1), 16); return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`; };
  const repoIdOf = (d) => (data.nodes.find((n) => n.id === d.id) || {}).repo_id || "";

  panelNode.addEventListener("click", async (e) => {
    if (e.target.closest("[data-close-panel]")) { selected = null; PGGraph.highlight(rendered, null); showEmpty(); return; }
    const go = e.target.closest("[data-goto]");
    if (go) {
      e.preventDefault();
      const id = +go.dataset.goto;
      if (rendered.nodeEls.has(id)) select(id, true);
      else if (mode === "detailed") location.href = `${base}/graph?focus=${id}`;
      else select(id, false, true);
      return;
    }
    const vb = e.target.closest("[data-verify]");
    const vn = e.target.closest("[data-verify-node]");
    if (!vb && !vn) return;
    const dlg = document.getElementById("verify-dialog");
    const isNode = !!vn, decision = vb ? vb.dataset.d : "CONFIRM";
    dlg.querySelector('[data-f="title"]').textContent = isNode ? "Подтвердить компонент" : decision === "CONFIRM" ? "Подтвердить связь" : "Отклонить связь";
    dlg.querySelector('[data-f="text"]').textContent = isNode
      ? "Подтверждённый компонент получит уверенность 1,0. Можно уточнить его назначение — описание сохранится и при следующих анализах."
      : decision === "CONFIRM" ? "Связь будет отмечена как проверенная архитектором и получит уверенность 1,0." : "Связь исчезнет с карты и не будет учитываться в impact analysis. Решение сохранится при следующих анализах.";
    dlg.querySelector('[data-f="desc-field"]').classList.toggle("hidden", !isNode);
    dlg.querySelector('[data-f="submit"]').textContent = decision === "REJECT" ? "Отклонить" : "Подтвердить";
    dlg.querySelector("#v-desc").value = "";
    dlg.returnValue = "";
    dlg.showModal();
    dlg.onclose = async () => {
      if (dlg.returnValue !== "ok") return;
      try {
        await PG.api(`/api/projects/${pid}/verifications`, { method: "POST", body: { subject: isNode ? "NODE" : "EDGE", id: +(vb ? vb.dataset.verify : vn.dataset.verifyNode), decision, description: isNode ? dlg.querySelector("#v-desc").value : null } });
        PG.toast(decision === "REJECT" ? "Связь отклонена" : "Подтверждено");
        const keep = selected;
        const params = new URLSearchParams();
        if (mode === "detailed") { if (data.repository_id) params.set("repo", data.repository_id); if (data.focus) params.set("focus", data.focus); }
        data = await PG.api(`/api/projects/${pid}/graph/${mode}?${params}`);
        render(true);
        if (keep) select(keep);
      } catch (err) { PG.toast(err.message, "error"); }
    };
  });

  /* поиск по графу */
  const sInput = document.getElementById("node-search"), sBox = document.getElementById("search-results");
  let timer;
  sInput?.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = sInput.value.trim();
      if (!q) { sBox.classList.add("hidden"); return; }
      const types = sInput.dataset.types ? `&types=${sInput.dataset.types}` : "";
      try {
        const rows = await PG.api(`/api/projects/${pid}/nodes/search?q=${encodeURIComponent(q)}${types}`);
        sBox.innerHTML = rows.map((r) => `<button type="button" data-id="${r.id}"><span class="grow ellipsis">${PG.esc(r.name)}</span><span class="tag">${PG.esc(r.type)}</span></button>`).join("") || '<div class="faint small" style="padding:8px">Ничего не найдено</div>';
        sBox.classList.remove("hidden");
      } catch (err) { PG.toast(err.message, "error"); }
    }, 160);
  });
  sBox?.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-id]");
    if (!b) return;
    const id = +b.dataset.id;
    sBox.classList.add("hidden"); sInput.value = "";
    if (rendered.nodeEls.has(id)) select(id, true);
    else if (mode === "detailed") location.href = `${base}/graph?focus=${id}`;
    else select(id, false, true);
  });
  document.addEventListener("click", (e) => { if (sBox && !e.target.closest(".search")) sBox.classList.add("hidden"); });

  document.querySelectorAll("[data-zoom]").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.zoom === "fit") vp.fit(rendered.box); else vp.zoomBy(b.dataset.zoom === "in" ? 1 / 1.25 : 1.25);
  }));
  ["show-low", "show-code", "show-ext"].forEach((id) => document.getElementById(id)?.addEventListener("change", () => render(true)));
  document.getElementById("repo-select")?.addEventListener("change", (e) => { location.href = `${base}/graph?repo=${e.target.value}`; });
  document.getElementById("focus-clear")?.addEventListener("click", () => { location.href = `${base}/graph?repo=${data.repository_id || ""}`; });
  window.addEventListener("resize", () => rendered && vp.fit(rendered.box));
  load();
})();

/* ================================================================ мини-карта в отчёте impact */
(async function impactMap() {
  const box = document.getElementById("impact-map");
  if (!box) return;
  const svg = box.querySelector("svg");
  const changed = new Set(JSON.parse(box.dataset.changed));
  const affected = new Map(JSON.parse(box.dataset.affected).map((a) => [a.id, a]));
  let data;
  try { data = await PG.api(`/api/projects/${box.dataset.pid}/graph/overview`); } catch (err) { box.classList.add("hidden"); return; }
  const r = PGGraph.draw(svg, data, { mode: "overview" });
  const vp = PGGraph.viewport(svg);
  vp.fit(r.box, 30);
  const hot = new Set([...changed, ...affected.keys()]);
  r.nodeEls.forEach((g, id) => {
    g.classList.toggle("changed", changed.has(id));
    g.classList.toggle("impact", affected.has(id));
    g.classList.toggle("dim", !hot.has(id));
  });
  r.edgeEls.forEach(({ e, p }) => {
    const on = hot.has(e.source) && hot.has(e.target);
    p.classList.toggle("hl", on);
    p.classList.toggle("dim", !on);
  });
})();
