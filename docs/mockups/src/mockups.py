"""Макеты экранов PortaGraph (HTML → PNG через Chromium)."""
import asyncio, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "diagrams" / "src"))
from playwright.async_api import async_playwright
from render import EXE

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:Inter,'DejaVu Sans',sans-serif;background:#e9ecef;color:#1b2559}
.screen{width:1440px;height:900px;display:flex;background:#f5f7fb;overflow:hidden;margin:20px;border-radius:10px;box-shadow:0 4px 24px rgba(0,0,0,.08)}
.side{width:232px;background:#141b3c;color:#c5cbe8;padding:22px 16px;display:flex;flex-direction:column;gap:4px;flex-shrink:0}
.logo{display:flex;align-items:center;gap:10px;color:#fff;font-weight:700;font-size:19px;margin-bottom:22px;padding-left:6px}
.logo i{width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,#4c6ef5,#f59f00);display:inline-block;position:relative}
.logo i:after{content:"";position:absolute;inset:8px;border:2px solid #fff;border-radius:50%}
.proj{background:#1f2853;border-radius:10px;padding:10px 12px;margin-bottom:14px;font-size:13px}
.proj b{display:block;color:#fff;font-size:14px;margin-bottom:2px}
.nav{padding:10px 12px;border-radius:8px;font-size:14px;display:flex;align-items:center;gap:10px}
.nav.on{background:#3b5bdb;color:#fff}
.nav .d{width:8px;height:8px;border-radius:50%;background:#5c6a9e}
.nav.on .d{background:#fff}
.nav .new{margin-left:auto;font-size:10px;background:#f59f00;color:#141b3c;border-radius:4px;padding:1px 5px;font-weight:700}
.sep{height:1px;background:#273061;margin:12px 0}
.user{margin-top:auto;display:flex;align-items:center;gap:10px;font-size:13px}
.av{width:32px;height:32px;border-radius:50%;background:#4c6ef5;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:13px}
.main{flex:1;display:flex;flex-direction:column;min-width:0}
.top{height:64px;background:#fff;border-bottom:1px solid #e3e7f1;display:flex;align-items:center;padding:0 28px;gap:16px}
.top h1{font-size:20px;font-weight:700}
.crumb{color:#8a94b8;font-size:13px}
.search{margin-left:auto;width:330px;height:38px;border:1px solid #dfe3ee;border-radius:9px;padding:0 14px;display:flex;align-items:center;color:#9aa3c2;font-size:13px}
.btn{white-space:nowrap;height:38px;padding:0 16px;border-radius:9px;background:#3b5bdb;color:#fff;font-size:14px;font-weight:600;display:inline-flex;align-items:center;gap:8px;border:none}
.btn.ghost{background:#fff;color:#3b5bdb;border:1px solid #c5d0fa}
.btn.amber{background:#f59f00;color:#141b3c}
.content{flex:1;padding:24px 28px;overflow:hidden;position:relative}
.card{background:#fff;border:1px solid #e3e7f1;border-radius:14px;padding:18px}
.muted{color:#8a94b8}.small{font-size:12px}
.tag{display:inline-block;font-size:11px;font-weight:600;padding:3px 8px;border-radius:6px}
.t-svc{background:#e7edff;color:#3b5bdb}.t-fe{background:#f3f0ff;color:#7048e8}.t-lib{background:#e6fcf5;color:#0ca678}
.t-inf{background:#fff4e6;color:#e8590c}.t-ok{background:#d3f9d8;color:#2b8a3e}.t-warn{background:#fff3bf;color:#a7690b}
.t-err{background:#ffe3e3;color:#c92a2a}.t-ai{background:#fff3bf;color:#a7690b}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
table{border-collapse:collapse;width:100%;font-size:13px}
th{text-align:left;color:#8a94b8;font-weight:600;font-size:12px;padding:10px 12px;border-bottom:1px solid #e3e7f1}
td{padding:11px 12px;border-bottom:1px solid #f0f2f7}
.bar{height:8px;background:#edf0f7;border-radius:5px;overflow:hidden}.bar i{display:block;height:100%;background:linear-gradient(90deg,#3b5bdb,#748ffc);border-radius:5px}
.step{display:flex;gap:14px;align-items:flex-start;padding:12px 0}
.dot{width:26px;height:26px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;flex-shrink:0}
.d-ok{background:#d3f9d8;color:#2b8a3e}.d-run{background:#3b5bdb;color:#fff}.d-wait{background:#edf0f7;color:#8a94b8}
.input{height:40px;border:1px solid #dfe3ee;border-radius:9px;padding:0 12px;display:flex;align-items:center;font-size:13px;background:#fff}
.label{font-size:12px;font-weight:600;color:#55618f;margin-bottom:6px}
.code{font-family:'DejaVu Sans Mono',monospace;font-size:12px;background:#0f1530;color:#c9d1f5;border-radius:10px;padding:14px;line-height:1.65}
.code .hl{background:#2b3a7a;display:block;margin:0 -14px;padding:0 14px}
.code .k{color:#ff8fab}.code .s{color:#8ce99a}.code .c{color:#6c7aa8}.code .n{color:#ffd43b}
.legend{display:flex;gap:16px;font-size:12px;color:#55618f;align-items:center}
.legend span{display:inline-flex;align-items:center;gap:6px}
.sw{width:12px;height:12px;border-radius:3px;display:inline-block}
.risk{font-size:28px;font-weight:800}
.chip{display:inline-flex;align-items:center;gap:6px;border:1px solid #dfe3ee;border-radius:20px;padding:5px 11px;font-size:12px;background:#fff}
"""

def shell(active, title, crumb, body, actions=""):
    items = [("map", "Карта системы", ""), ("graph", "Граф зависимостей", ""), ("ask", "AI-ассистент", ""),
             ("impact", "Impact analysis", "AI"), ("docs", "Документация", "AI"), ("repos", "Репозитории", ""),
             ("settings", "Настройки", "")]
    nav = "".join(f'<div class="nav{" on" if k == active else ""}"><span class="d"></span>{t}'
                  f'{f"<span class=new>{b}</span>" if b else ""}</div>' for k, t, b in items)
    return f"""<div class="screen"><aside class="side"><div class="logo"><i></i>PortaGraph</div>
<div class="proj"><span class="muted small">Проект</span><b>ShopFlow Platform</b><span class="small">9 репозиториев · обновлено 12 мин назад</span></div>
<div class="nav{" on" if active == "projects" else ""}"><span class="d"></span>Все проекты</div><div class="sep"></div>{nav}
<div class="user"><div class="av">АК</div><div>Анастасия К.<br><span class="muted small">Архитектор</span></div></div></aside>
<main class="main"><div class="top"><div><div class="crumb">{crumb}</div><h1>{title}</h1></div>
<div class="search">⌕&nbsp; Поиск по сервисам, классам, файлам…</div>{actions}</div>
<div class="content">{body}</div></main></div>"""

# ------------------------------------------------------------------ граф (SVG)
COL = {"svc": ("#e7edff", "#3b5bdb"), "fe": ("#f3f0ff", "#7048e8"), "db": ("#e6fcf5", "#0ca678"),
       "q": ("#fff4e6", "#e8590c"), "ext": ("#f1f3f5", "#868e96"), "lib": ("#e6fcf5", "#0ca678"),
       "cls": ("#ffffff", "#495057"), "hit1": ("#ffe3e3", "#e03131"), "hit2": ("#fff3bf", "#f08c00"),
       "src": ("#ffe8a3", "#d9480f")}

def svg_graph(nodes, edges, w, h, sel=None):
    out = [f'<svg width="100%" style="display:block" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" font-family="Inter,DejaVu Sans">',
           '<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">'
           '<path d="M0,0 L10,5 L0,10 z" fill="#7a86b6"/></marker>'
           '<marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">'
           '<path d="M0,0 L10,5 L0,10 z" fill="#e03131"/></marker>'
           '<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#dde2ef"/></pattern></defs>',
           f'<rect width="{w}" height="{h}" fill="url(#dots)"/>']
    pos = {n[0]: n for n in nodes}
    for e in edges:
        a, b, lab = e[0], e[1], e[2]
        style = e[3] if len(e) > 3 else ""
        _, ax, ay, aw, *_ = pos[a]
        _, bx, by, bw, *_ = pos[b]
        x1, y1 = ax + aw / 2, ay + 24
        x2, y2 = bx + bw / 2, by + 24
        # обрезка по прямоугольникам
        def clip(cx, cy, tx, ty, hw):
            dx, dy = tx - cx, ty - cy
            if dx == 0 and dy == 0:
                return cx, cy
            s = min(hw / abs(dx) if dx else 1e9, 24 / abs(dy) if dy else 1e9)
            return cx + dx * s, cy + dy * s
        sx, sy = clip(x1, y1, x2, y2, aw / 2)
        tx, ty = clip(x2, y2, x1, y1, bw / 2 + 4)
        color = "#e03131" if style == "hot" else "#9aa5cf"
        dash = ' stroke-dasharray="6 5"' if style in ("dash", "async") else ""
        mk = "arr" if style == "hot" else "ar"
        wdt = 2.6 if style == "hot" else 1.6
        out.append(f'<line x1="{sx:.0f}" y1="{sy:.0f}" x2="{tx:.0f}" y2="{ty:.0f}" stroke="{color}" stroke-width="{wdt}"{dash} marker-end="url(#{mk})"/>')
        if lab:
            mx, my = (sx + tx) / 2, (sy + ty) / 2
            tw = len(lab) * 6.2 + 10
            out.append(f'<rect x="{mx-tw/2:.0f}" y="{my-9:.0f}" width="{tw:.0f}" height="17" rx="8" fill="#fff" stroke="#e3e7f1"/>'
                       f'<text x="{mx:.0f}" y="{my+3:.0f}" font-size="10.5" text-anchor="middle" fill="#55618f">{lab}</text>')
    for nid, x, y, wd, label, kind, sub in nodes:
        f, s = COL[kind]
        sw = 3 if nid == sel else 1.6
        shadow = ' filter="drop-shadow(0 4px 10px rgba(59,91,219,.35))"' if nid == sel else ""
        if kind == "db":
            out.append(f'<g{shadow}><rect x="{x}" y="{y}" width="{wd}" height="48" rx="12" fill="{f}" stroke="{s}" stroke-width="{sw}"/>'
                       f'<ellipse cx="{x+20}" cy="{y+17}" rx="8" ry="3.5" fill="none" stroke="{s}" stroke-width="1.6"/>'
                       f'<path d="M{x+12},{y+17} v13 a8,3.5 0 0 0 16,0 v-13" fill="none" stroke="{s}" stroke-width="1.6"/></g>')
        else:
            out.append(f'<rect x="{x}" y="{y}" width="{wd}" height="48" rx="12" fill="{f}" stroke="{s}" stroke-width="{sw}"{shadow}/>'
                       f'<circle cx="{x+20}" cy="{y+24}" r="7" fill="{s}" opacity=".9"/>')
        out.append(f'<text x="{x+36}" y="{y+21}" font-size="13" font-weight="600" fill="#1b2559">{label}</text>'
                   f'<text x="{x+36}" y="{y+37}" font-size="10.5" fill="#7a86b6">{sub}</text>')
    out.append("</svg>")
    return "".join(out)

MAP_NODES = [
 ("web", 40, 250, 170, "web-frontend", "fe", "Next.js · фронтенд"),
 ("gw", 280, 250, 170, "api-gateway", "svc", "Spring Cloud Gateway"),
 ("auth", 540, 90, 170, "auth-service", "svc", "JWT, пользователи"),
 ("cat", 280, 110, 170, "catalog-service", "svc", "каталог товаров"),
 ("ord", 540, 330, 170, "order-service", "svc", "заказы"),
 ("bill", 540, 460, 170, "billing-service", "svc", "платежи"),
 ("kafka", 800, 400, 170, "Kafka", "q", "orders.created, payments.done"),
 ("notif", 800, 530, 175, "notification-svc", "svc", "email, push"),
 ("pg1", 800, 90, 150, "users-db", "db", "PostgreSQL"),
 ("pg2", 800, 260, 150, "orders-db", "db", "PostgreSQL"),
 ("pay", 280, 460, 170, "ЮKassa API", "ext", "внешняя система"),
]
MAP_EDGES = [("web", "gw", "HTTP"), ("gw", "auth", "HTTP"), ("gw", "cat", "HTTP"), ("gw", "ord", "HTTP"),
             ("ord", "auth", "HTTP", "dash"), ("auth", "pg1", ""), ("ord", "pg2", ""), ("ord", "kafka", "publish", "async"),
             ("bill", "kafka", "publish", "async"), ("kafka", "notif", "consume", "async"), ("bill", "pay", "HTTP")]

# ------------------------------------------------------------------ экраны
def s_projects():
    cards = ""
    data = [("ShopFlow Platform", "9 репозиториев · 4 214 файлов", "t-ok", "Анализ завершён", "12 мин назад", 100),
            ("Банк: процессинг карт", "14 репозиториев · 11 932 файла", "t-warn", "Идёт анализ · 64%", "сейчас", 64),
            ("Внутренний портал HR", "3 репозитория · 812 файлов", "t-ok", "Анализ завершён", "вчера", 100),
            ("Legacy CRM", "6 репозиториев · 7 405 файлов", "t-err", "Ошибка доступа к 1 репозиторию", "2 дня назад", 100)]
    for n, sub, t, st, upd, p in data:
        cards += f"""<div class="card" style="display:flex;flex-direction:column;gap:12px">
<div style="display:flex;justify-content:space-between;align-items:center"><b style="font-size:16px">{n}</b><span class="tag {t}">{st}</span></div>
<div class="muted small">{sub}</div><div class="bar"><i style="width:{p}%"></i></div>
<div style="display:flex;gap:8px;flex-wrap:wrap"><span class="tag t-svc">SERVICE ×5</span><span class="tag t-fe">FRONTEND</span><span class="tag t-lib">LIBRARY</span></div>
<div class="muted small">Обновлено: {upd}</div></div>"""
    body = f"""<div class="grid2" style="grid-template-columns:repeat(2,1fr)">{cards}</div>
<div class="card" style="margin-top:18px;display:flex;align-items:center;gap:18px;border-style:dashed;border-color:#b6c3f7;background:#f8faff">
<div class="dot d-run" style="width:44px;height:44px;font-size:22px">+</div><div><b>Новый проект</b><div class="muted small">Подключите набор репозиториев — роли сервисов и связи PortaGraph определит сам</div></div>
<div style="margin-left:auto" class="btn">Создать проект</div></div>"""
    return shell("projects", "Мои проекты", "Главная", body, '<div class="btn">+ Новый проект</div>')

def s_connect():
    rows = [("github.com/shopflow/api-gateway", "t-ok", "Подключён"), ("github.com/shopflow/auth-service", "t-ok", "Подключён"),
            ("github.com/shopflow/order-service", "t-ok", "Подключён"), ("github.com/shopflow/billing-service", "t-ok", "Подключён"),
            ("bitbucket.org/shopflow/catalog-service", "t-ok", "Подключён"), ("github.com/shopflow/web-frontend", "t-ok", "Подключён"),
            ("github.com/shopflow/common-dto", "t-ok", "Подключён"), ("github.com/shopflow/notification-svc", "t-err", "Нет доступа: токен без прав чтения"),
            ("github.com/shopflow/infra", "t-ok", "Подключён")]
    tr = "".join(f'<tr><td>{u}</td><td><span class="tag {t}">{s}</span></td></tr>' for u, t, s in rows)
    body = f"""<div style="display:flex;gap:30px;margin-bottom:22px;align-items:center">
<div class="step" style="padding:0"><div class="dot d-ok">✓</div><div><b>Проект</b><div class="muted small">ShopFlow Platform</div></div></div>
<div style="flex:0 0 60px;height:2px;background:#c5d0fa"></div>
<div class="step" style="padding:0"><div class="dot d-run">2</div><div><b>Репозитории</b><div class="muted small">адреса и доступ</div></div></div>
<div style="flex:0 0 60px;height:2px;background:#e3e7f1"></div>
<div class="step" style="padding:0"><div class="dot d-wait">3</div><div><b>Анализ</b><div class="muted small">индексация и граф</div></div></div></div>
<div class="grid2" style="grid-template-columns:420px 1fr">
<div class="card" style="display:flex;flex-direction:column;gap:16px">
<div><div class="label">Адреса репозиториев (по одному в строке)</div>
<div class="code" style="background:#f8f9fc;color:#1b2559;border:1px solid #dfe3ee;height:250px">https://github.com/shopflow/api-gateway<br>https://github.com/shopflow/auth-service<br>https://github.com/shopflow/order-service<br>https://github.com/shopflow/billing-service<br>https://bitbucket.org/shopflow/catalog-service<br>https://github.com/shopflow/web-frontend<br>https://github.com/shopflow/common-dto<br>https://github.com/shopflow/notification-svc<br>https://github.com/shopflow/infra</div></div>
<div><div class="label">Токен доступа (только чтение)</div><div class="input">●●●●●●●●●●●●●●●●●●●●●●●●</div>
<div class="muted small" style="margin-top:6px">Хранится в зашифрованном виде (AES-256-GCM) и не попадает в индекс</div></div>
<div style="background:#f3f6ff;border-radius:10px;padding:12px" class="small">💡 Роли репозиториев указывать не нужно — сервисы, библиотеки и фронтенд система определит сама.</div>
<div style="display:flex;gap:10px"><div class="btn ghost">Назад</div><div class="btn" style="flex:1;justify-content:center">Проверить доступ</div></div></div>
<div class="card"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><b>Результат проверки</b><span class="muted small">8 из 9 подключены</span></div>
<table><tr><th>Репозиторий</th><th>Статус</th></tr>{tr}</table>
<div style="display:flex;gap:10px;margin-top:18px;justify-content:flex-end"><div class="btn ghost">Исправить адрес</div><div class="btn">Запустить анализ →</div></div></div></div>"""
    return shell("repos", "Подключение репозиториев", "Новый проект · шаг 2 из 3", body)

def s_progress():
    steps = [("d-ok", "✓", "Загрузка коммитов", "9 репозиториев, основная ветка main", "4 c"),
             ("d-ok", "✓", "Индексация кода и документации", "4 214 файлов · 18 930 фрагментов · скрыто секретов: 3", "2 мин 41 c"),
             ("d-run", "3", "Агентный анализ архитектуры", "Определяем назначение репозиториев: 6 из 9", "идёт…"),
             ("d-wait", "4", "Построение единого графа", "Поиск межсервисных связей и проверка агентом", "ожидание")]
    st = "".join(f'<div class="step" style="border-bottom:1px solid #f0f2f7"><div class="dot {c}">{n}</div><div style="flex:1"><b>{t}</b>'
                 f'<div class="muted small">{s}</div></div><div class="muted small">{tm}</div></div>' for c, n, t, s, tm in steps)
    log = """<span class="c">14:02:11</span> auth-service → <span class="n">SERVICE</span> (0.93) «Аутентификация и выдача JWT»<br>
<span class="c">14:02:19</span> common-dto → <span class="n">LIBRARY</span> (0.88) «Общие DTO и контракты событий»<br>
<span class="c">14:02:26</span> web-frontend → <span class="n">FRONTEND</span> (0.97) «Витрина магазина на Next.js»<br>
<span class="c">14:02:34</span> order-service → <span class="n">SERVICE</span> (0.91) «Оформление и жизненный цикл заказов»<br>
<span class="c">14:02:41</span> infra → <span class="n">INFRASTRUCTURE</span> (0.84) «Terraform и Helm-чарты»<br>
<span class="c">14:02:49</span> billing-service → <span class="n">SERVICE</span> (0.90) «Платежи через ЮKassa»<br><span class="hl">14:02:55 catalog-service: анализ README и openapi.yaml…</span>"""
    body = f"""<div class="grid2" style="grid-template-columns:1fr 520px">
<div class="card"><div style="display:flex;justify-content:space-between;align-items:baseline"><b style="font-size:17px">Анализ проекта ShopFlow Platform</b><span class="tag t-warn">ANALYZING</span></div>
<div style="display:flex;align-items:center;gap:14px;margin:16px 0 8px"><div class="bar" style="flex:1;height:12px"><i style="width:68%"></i></div><b>68%</b></div>
<div class="muted small" style="margin-bottom:10px">Примерно 2 минуты до завершения · можно закрыть вкладку, мы пришлём уведомление</div>{st}
<div style="display:flex;gap:10px;margin-top:18px"><div class="btn ghost">Отменить</div><div class="btn ghost">Свернуть</div></div></div>
<div class="card"><b>Журнал агента</b><div class="muted small" style="margin:4px 0 12px">Выводы агента — гипотезы: их можно подтвердить или исправить после анализа</div>
<div class="code" style="height:420px">{log}</div></div></div>"""
    return shell("map", "Прогресс анализа", "ShopFlow Platform", body)

def s_map():
    g = svg_graph(MAP_NODES, MAP_EDGES, 1000, 600, sel="ord")
    panel = """<div class="card" style="width:330px;flex-shrink:0;display:flex;flex-direction:column;gap:12px">
<div style="display:flex;justify-content:space-between"><span class="tag t-svc">SERVICE</span><span class="tag t-ai">AI · уверенность 0.91</span></div>
<b style="font-size:18px">order-service</b>
<div class="small" style="line-height:1.55">Оформление заказов и управление их жизненным циклом. Публикует событие <b>orders.created</b>, проверяет пользователя через auth-service.</div>
<div class="muted small">Репозиторий: github.com/shopflow/order-service</div>
<div class="sep" style="background:#eef0f6;margin:2px 0"></div>
<div class="label" style="margin:0">Зависит от (3)</div>
<div style="display:flex;gap:6px;flex-wrap:wrap"><span class="chip">auth-service · HTTP</span><span class="chip">orders-db</span><span class="chip">Kafka · publish</span></div>
<div class="label" style="margin:0">Используют (2)</div>
<div style="display:flex;gap:6px;flex-wrap:wrap"><span class="chip">api-gateway</span><span class="chip">notification-svc</span></div>
<div class="label" style="margin:0">Доказательство связи с auth-service</div>
<div class="code" style="padding:10px;font-size:11px">AuthClient.java:27<br><span class="s">"http://auth-service:8080/api/v1/users"</span></div>
<div style="display:flex;gap:8px;margin-top:auto"><div class="btn ghost" style="flex:1;justify-content:center;padding:0 8px">✓ Подтвердить</div><div class="btn amber" style="flex:1;justify-content:center;padding:0 8px">Оценить влияние</div></div></div>"""
    body = f"""<div style="display:flex;gap:10px;margin-bottom:14px;align-items:center">
<div class="btn" style="height:34px">Карта системы</div><div class="btn ghost" style="height:34px">Граф зависимостей кода</div>
<div class="legend" style="margin-left:24px"><span><i class="sw" style="background:#3b5bdb"></i>сервис</span><span><i class="sw" style="background:#7048e8"></i>фронтенд</span>
<span><i class="sw" style="background:#0ca678"></i>БД</span><span><i class="sw" style="background:#e8590c"></i>очередь</span><span><i class="sw" style="background:#868e96"></i>внешняя</span>
<span>- - - асинхронно / уверенность &lt; 0.7</span></div></div>
<div style="display:flex;gap:18px"><div class="card" style="padding:0;overflow:hidden;flex:1">{g}</div>{panel}</div>"""
    return shell("map", "Карта системы", "ShopFlow Platform", body, '<div class="btn ghost">Экспорт PNG</div>')

def s_graph():
    nodes = [("c1", 40, 60, 210, "OrderController", "cls", "web · REST /api/orders"),
             ("c2", 330, 60, 200, "OrderService", "cls", "service · бизнес-логика"),
             ("c3", 620, 20, 200, "AuthClient", "cls", "client · HTTP → auth"),
             ("c4", 620, 120, 210, "OrderRepository", "cls", "JPA · orders-db"),
             ("c5", 620, 220, 210, "OrderEventPublisher", "cls", "Kafka · orders.created"),
             ("c6", 330, 220, 200, "PricingPolicy", "cls", "domain"),
             ("c7", 40, 220, 210, "OrderMapper", "cls", "common-dto"),
             ("c8", 330, 380, 200, "Order", "cls", "entity"),
             ("c9", 620, 380, 210, "OrderCreatedEvent", "lib", "common-dto · библиотека")]
    edges = [("c1", "c2", "calls"), ("c1", "c7", "uses"), ("c2", "c3", "calls"), ("c2", "c4", "uses"), ("c2", "c5", "uses"),
             ("c2", "c6", "uses"), ("c4", "c8", "manages"), ("c5", "c9", "imports"), ("c7", "c8", "maps")]
    g = svg_graph(nodes, edges, 880, 470, sel="c2")
    code = """<span class="c">// OrderService.java  (order-service)</span><br><span class="k">@Service</span><br><span class="k">public class</span> <span class="n">OrderService</span> {<br>
&nbsp;&nbsp;<span class="k">private final</span> AuthClient auth;<br>&nbsp;&nbsp;<span class="k">private final</span> OrderRepository orders;<br><br>
<span class="hl">&nbsp;&nbsp;<span class="k">public</span> Order create(CreateOrder cmd) {</span><span class="hl">&nbsp;&nbsp;&nbsp;&nbsp;var user = auth.findUser(cmd.userId());</span>
&nbsp;&nbsp;&nbsp;&nbsp;var order = pricing.apply(cmd, user);<br>&nbsp;&nbsp;&nbsp;&nbsp;orders.save(order);<br>&nbsp;&nbsp;&nbsp;&nbsp;events.publish(order);<br>&nbsp;&nbsp;&nbsp;&nbsp;<span class="k">return</span> order;<br>&nbsp;&nbsp;}<br>}"""
    body = f"""<div style="display:flex;gap:10px;margin-bottom:14px;align-items:center">
<div class="btn ghost" style="height:34px">Карта системы</div><div class="btn" style="height:34px">Граф зависимостей кода</div>
<span class="chip" style="margin-left:16px">Сервис: order-service ▾</span><span class="chip">Глубина: 2 ▾</span><span class="chip">Типы: классы, сущности ▾</span></div>
<div style="display:flex;gap:18px"><div class="card" style="padding:0;overflow:hidden;width:700px;flex-shrink:0">{g}</div>
<div class="card" style="flex:1;display:flex;flex-direction:column;gap:10px"><b>OrderService</b><div class="muted small">order-service/src/main/java/…/OrderService.java · строки 14–41</div>
<div class="code">{code}</div><div class="small">Входящие: 1 · Исходящие: 5 · Межсервисных вызовов: 1</div>
<div class="btn ghost" style="justify-content:center">Открыть файл целиком</div></div></div>"""
    return shell("graph", "Граф зависимостей кода", "ShopFlow Platform", body)

def s_ask():
    body = """<div style="display:flex;gap:18px;height:100%">
<div class="card" style="width:260px;flex-shrink:0"><b>Диалоги</b><div style="margin-top:12px;display:flex;flex-direction:column;gap:8px" class="small">
<div style="background:#eef3ff;border-radius:8px;padding:9px">Где проверяется JWT и кто его использует?</div><div style="padding:9px">Как устроена оплата заказа?</div>
<div style="padding:9px">Какие сервисы пишут в orders-db?</div><div style="padding:9px">С чего начать новичку в billing?</div></div></div>
<div class="card" style="flex:1;display:flex;flex-direction:column;gap:16px">
<div style="align-self:flex-end;max-width:620px;background:#3b5bdb;color:#fff;border-radius:14px 14px 4px 14px;padding:12px 16px;font-size:14px">Где проверяется JWT и какие сервисы от этого зависят?</div>
<div style="max-width:820px;border:1px solid #e3e7f1;border-radius:14px 14px 14px 4px;padding:16px;font-size:14px;line-height:1.6">
JWT выпускается и проверяется в <b>auth-service</b>: подпись проверяет класс <code>JwtVerifier</code>, а фильтр <code>JwtAuthFilter</code> подключён в цепочку Spring Security.
Остальные сервисы токен сами не проверяют: <b>api-gateway</b> передаёт его в auth-service через <code>/api/v1/token/introspect</code>, а <b>order-service</b> вызывает auth-service через <code>AuthClient</code>.
Если изменить формат токена, затронуты gateway и order-service.
<div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">
<span class="chip">📄 auth-service/…/JwtVerifier.java:18–52</span><span class="chip">📄 auth-service/…/SecurityConfig.java:31–44</span>
<span class="chip">📄 api-gateway/…/TokenRelayFilter.java:22–40</span><span class="chip">📄 order-service/…/AuthClient.java:20–35</span></div>
<div style="margin-top:12px;display:flex;gap:8px"><span class="tag t-ok">Опирается на 4 фрагмента кода</span><span class="tag t-svc">Показать на карте</span><span class="tag t-ai">Оценить влияние изменения</span></div></div>
<div style="margin-top:auto;display:flex;gap:10px"><div class="input" style="flex:1;color:#9aa3c2">Спросите о проекте: «какие сервисы читают топик orders.created?»</div><div class="btn">Спросить</div></div>
<div class="muted small">Ответы AI вспомогательные: проверяйте источники. Ассистент видит только код этого проекта.</div></div></div>"""
    return shell("ask", "AI-ассистент", "ShopFlow Platform", body)

def s_impact():
    nodes = [("auth", 300, 40, 180, "auth-service", "src", "изменяемый компонент"),
             ("gw", 40, 180, 170, "api-gateway", "hit1", "расстояние 1 · 0.60"),
             ("ord", 300, 180, 180, "order-service", "hit1", "расстояние 1 · 0.54"),
             ("bill", 560, 180, 170, "billing-service", "hit2", "расстояние 2 · 0.26"),
             ("web", 40, 320, 170, "web-frontend", "hit2", "расстояние 2 · 0.36"),
             ("notif", 300, 320, 180, "notification-svc", "hit2", "расстояние 2 · 0.29"),
             ("cat", 40, 40, 170, "catalog-service", "svc", "не затронут")]
    edges = [("gw", "auth", "HTTP", "hot"), ("ord", "auth", "HTTP", "hot"), ("web", "gw", "HTTP", "hot"),
             ("notif", "ord", "consume", "hot"), ("bill", "ord", "consume", "hot"), ("gw", "cat", "HTTP")]
    g = svg_graph(nodes, edges, 770, 400)
    rows = [("api-gateway", "SERVICE", "1", "0.60", "auth-service → api-gateway"), ("order-service", "SERVICE", "1", "0.54", "auth-service → order-service"),
            ("web-frontend", "FRONTEND", "2", "0.36", "… → api-gateway → web-frontend"), ("notification-svc", "SERVICE", "2", "0.29", "… → order-service → notification-svc"),
            ("billing-service", "SERVICE", "2", "0.26", "… → order-service → billing-service")]
    tr = "".join(f"<tr><td><b>{a}</b></td><td><span class='tag t-svc'>{b}</span></td><td>{c}</td><td>{d}</td><td class='muted'>{e}</td></tr>" for a, b, c, d, e in rows)
    body = f"""<div class="card" style="display:flex;gap:14px;align-items:flex-end;margin-bottom:16px">
<div style="flex:1"><div class="label">Описание изменения</div><div class="input">Перейти с HS256 на RS256 и добавить claim «tenant_id» в JWT</div></div>
<div><div class="label">Компоненты</div><div class="input" style="gap:6px"><span class="tag t-svc">auth-service ✕</span></div></div>
<div><div class="label">Глубина</div><div class="input" style="width:80px">3 ▾</div></div><div class="btn amber">Оценить влияние</div></div>
<div style="display:flex;gap:18px"><div class="card" style="padding:0;overflow:hidden;width:560px;flex-shrink:0">{g}</div>
<div style="flex:1;display:flex;flex-direction:column;gap:16px">
<div class="card" style="display:flex;gap:18px;align-items:center"><div><div class="muted small">Уровень риска</div><div class="risk" style="color:#e03131">HIGH</div></div>
<div class="small" style="line-height:1.5">Прямо затронуты 2 сервиса, всего 5 компонентов. <b>Рекомендация AI:</b> обновить проверку подписи в TokenRelayFilter (gateway) и AuthClient (order-service), выпустить их до auth-service; предупредить владельцев web-frontend.</div></div>
<div class="card" style="padding:8px 6px"><table><tr><th>Компонент</th><th>Тип</th><th>Шаг</th><th>Вес</th><th>Путь</th></tr>{tr}</table></div></div></div>"""
    return shell("impact", "Impact analysis", "ShopFlow Platform", body, '<div class="btn ghost">История отчётов</div>')

def s_docs():
    body = """<div style="display:flex;gap:18px;height:100%">
<div class="card" style="width:300px;flex-shrink:0;display:flex;flex-direction:column;gap:10px"><b>Документы проекта</b>
<div style="background:#eef3ff;border-radius:10px;padding:11px"><b class="small">Онбординг: как устроен ShopFlow</b><br><span class="tag t-ok" style="margin-top:6px">Утверждён</span> <span class="muted small">А. Казанкова</span></div>
<div style="border:1px solid #eef0f6;border-radius:10px;padding:11px"><b class="small">Архитектура системы</b><br><span class="tag t-warn" style="margin-top:6px">Черновик AI</span></div>
<div style="border:1px solid #eef0f6;border-radius:10px;padding:11px"><b class="small">Карточки сервисов</b><br><span class="tag t-err" style="margin-top:6px">Устарел</span> <span class="muted small">после анализа 27.10</span></div>
<div style="margin-top:auto" class="label">Сформировать новый</div>
<div class="input">Онбординг-гайд ▾</div><div class="btn" style="justify-content:center">Сформировать</div></div>
<div class="card" style="flex:1;padding:28px 36px;font-size:14px;line-height:1.65;overflow:hidden">
<div style="display:flex;justify-content:space-between;align-items:center"><span class="tag t-ok">Утверждён архитектором · 27.10.2026</span><div style="display:flex;gap:8px"><div class="btn ghost" style="height:32px">Экспорт .md</div><div class="btn ghost" style="height:32px">Экспорт PDF</div></div></div>
<h2 style="font-size:24px;margin:16px 0 6px">Онбординг: как устроен ShopFlow</h2><div class="muted small">Сформировано по графу анализа №42 · 9 репозиториев · 7 сервисов</div>
<h3 style="font-size:16px;margin:18px 0 6px">1. Система за одну минуту</h3>
<p>ShopFlow — интернет-витрина с микросервисной архитектурой. Запросы клиентов из <b>web-frontend</b> идут через <b>api-gateway</b> к сервисам каталога, заказов и аутентификации. Оплата и уведомления работают асинхронно через Kafka.</p>
<h3 style="font-size:16px;margin:18px 0 6px">2. Ключевые сервисы</h3>
<table style="font-size:13px"><tr><th>Сервис</th><th>Назначение</th><th>Данные</th><th>С чего начать читать</th></tr>
<tr><td><b>auth-service</b></td><td>пользователи, JWT</td><td>users-db</td><td>JwtVerifier.java</td></tr>
<tr><td><b>order-service</b></td><td>жизненный цикл заказа</td><td>orders-db, orders.created</td><td>OrderService.java</td></tr>
<tr><td><b>billing-service</b></td><td>платежи через ЮKassa</td><td>payments.done</td><td>PaymentFlow.java</td></tr></table>
<h3 style="font-size:16px;margin:18px 0 6px">3. Путь заказа</h3>
<p>web-frontend → api-gateway → order-service → (Kafka: orders.created) → billing-service → (payments.done) → notification-svc.</p></div></div>"""
    return shell("docs", "Документация и онбординг", "ShopFlow Platform", body)

SCREENS = [("m01_projects", s_projects), ("m02_connect", s_connect), ("m03_progress", s_progress), ("m04_map", s_map),
           ("m05_graph", s_graph), ("m06_assistant", s_ask), ("m07_impact", s_impact), ("m08_docs", s_docs)]

async def main():
    out = pathlib.Path(__file__).resolve().parents[1]
    html = f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>" + \
           "".join(f'<div id="{n}">{f()}</div>' for n, f in SCREENS) + "</body></html>"
    (out / "src" / "mockups.html").write_text(html, encoding="utf-8")
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=EXE)
        pg = await b.new_page(device_scale_factor=1.5, viewport={"width": 1500, "height": 1000})
        await pg.goto((out / "src" / "mockups.html").as_uri())
        await pg.wait_for_timeout(400)
        for n, _ in SCREENS:
            await pg.locator(f"#{n} .screen").screenshot(path=str(out / f"{n}.png"))
        await b.close()
    print("mockups ok")

asyncio.run(main())
