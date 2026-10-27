"""UML-диаграмма вариантов использования PortaGraph с ручной раскладкой (SVG)."""
import math

W, H = 1640, 1330
RX, RY = 128, 36
BLUE_F, BLUE_S = "#eef3fb", "#2f4ac0"
UNIQ_F, UNIQ_S = "#ffe8a3", "#d9480f"

ucs = {  # id: (x, y, текст, уникальный?)
    "UC-01": (430, 128, "Зарегистрироваться\nи войти", False),
    "UC-02": (430, 225, "Создать проект", False),
    "UC-15": (430, 315, "Управлять участниками\nпроекта", False),
    "UC-03": (430, 430, "Подключить набор\nрепозиториев", False),
    "UC-04": (430, 575, "Запустить анализ\nпроекта", False),
    "UC-13": (430, 680, "Подтвердить или\nисправить выводы AI", False),
    "UC-08": (430, 800, "Просмотреть карту\nсистемы", False),
    "UC-09": (430, 900, "Исследовать граф\nзависимостей кода", False),
    "UC-10": (430, 1000, "Задать вопрос\nAI-ассистенту", False),
    "UC-11": (430, 1100, "Выполнить\nimpact analysis", True),
    "UC-12": (430, 1200, "Сформировать описание\nархитектуры / онбординг", True),
    "UC-03.1": (830, 430, "Проверить доступ\nк репозиторию", False),
    "UC-05": (830, 535, "Проиндексировать код\nи документацию", False),
    "UC-06": (830, 640, "Выполнить агентный\nанализ архитектуры", True),
    "UC-07": (830, 760, "Построить единый граф\nархитектуры (multi-repo)", True),
    "UC-14": (1200, 600, "Синхронизировать\nпроект по webhook", False),
}
actors = {  # id: (x, y — центр фигуры, подпись)
    "guest": (95, 128, ["Гость"]),
    "owner": (95, 330, ["Владелец", "проекта"]),
    "arch": (95, 625, ["Архитектор /", "техлид"]),
    "dev": (95, 1000, ["Разработчик"]),
    "git": (1530, 470, ["«system»", "Git-хостинг", "(GitHub, Bitbucket)"]),
    "llm": (1530, 1080, ["«system»", "LLM-провайдер"]),
}
assoc = [("guest", "UC-01"), ("owner", "UC-02"), ("owner", "UC-15"), ("owner", "UC-03"),
         ("arch", "UC-04"), ("arch", "UC-13"),
         ("dev", "UC-08"), ("dev", "UC-09"), ("dev", "UC-10"), ("dev", "UC-11"), ("dev", "UC-12"),
         ("UC-03.1", "git"), ("UC-05", "git"), ("UC-14", "git"),
         ("UC-06", "llm"), ("UC-10", "llm"), ("UC-12", "llm")]
deps = [("UC-03", "UC-03.1", "«include»"), ("UC-03", "UC-04", "«include»"),
        ("UC-04", "UC-05", "«include»"), ("UC-04", "UC-06", "«include»"), ("UC-04", "UC-07", "«include»"),
        ("UC-14", "UC-05", "«include»"), ("UC-14", "UC-07", "«include»"),
        ("UC-09", "UC-08", "«extend»")]
gens = [("owner", "arch"), ("arch", "dev")]  # потомок -> родитель


def ell_point(cx, cy, tx, ty):
    """Точка на границе эллипса UC в направлении (tx, ty)."""
    dx, dy = tx - cx, ty - cy
    t = 1 / math.sqrt((dx / RX) ** 2 + (dy / RY) ** 2)
    return cx + dx * t, cy + dy * t


def anchor(node, toward):
    if node in ucs:
        x, y = ucs[node][:2]
        return ell_point(x, y, *toward)
    x, y = actors[node][:2]
    # точка на «плече» фигуры актёра
    return (x + (38 if toward[0] > x else -38), y - 6)


def center(node):
    return ucs[node][:2] if node in ucs else actors[node][:2]


out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
       f'font-family="DejaVu Sans, Arial" style="background:#fff">',
       '<defs>'
       '<marker id="vee" viewBox="0 0 12 12" refX="11" refY="6" markerWidth="11" markerHeight="11" orient="auto">'
       '<path d="M1,1 L11,6 L1,11" fill="none" stroke="#444" stroke-width="1.6"/></marker>'
       '<marker id="tri" viewBox="0 0 16 16" refX="15" refY="8" markerWidth="16" markerHeight="16" orient="auto">'
       '<path d="M1,1 L15,8 L1,15 Z" fill="#fff" stroke="#222" stroke-width="1.4"/></marker>'
       '</defs>',
       f'<rect x="0" y="0" width="{W}" height="{H}" fill="#fff"/>',
       # граница системы
       '<rect x="270" y="45" width="1090" height="1210" rx="14" fill="none" stroke="#333" stroke-width="1.6"/>',
       '<text x="290" y="75" font-size="19" font-weight="bold" fill="#222">PortaGraph</text>']

# ассоциации
for a, b in assoc:
    p1 = anchor(a, center(b))
    p2 = anchor(b, center(a))
    out.append(f'<line x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" x2="{p2[0]:.1f}" y2="{p2[1]:.1f}" stroke="#333" stroke-width="1.3"/>')

# include / extend
for a, b, lab in deps:
    p1 = anchor(a, center(b))
    p2 = anchor(b, center(a))
    out.append(f'<line x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" x2="{p2[0]:.1f}" y2="{p2[1]:.1f}" stroke="#444" '
               f'stroke-width="1.3" stroke-dasharray="7,5" marker-end="url(#vee)"/>')
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    if (a, b) == ("UC-03", "UC-04"):
        mx += 42
    if (a, b) == ("UC-09", "UC-08"):
        mx += 38
    out.append(f'<rect x="{mx-34}" y="{my-10}" width="68" height="17" fill="#fff" opacity="0.9"/>'
               f'<text x="{mx}" y="{my+3}" font-size="12" text-anchor="middle" fill="#444">{lab}</text>')

# UC-11 -> UC-07: ломаная в обход UC-10
p2 = ell_point(830, 760, 700, 1100)
out.append(f'<polyline points="558,1100 700,1100 {p2[0]:.1f},{p2[1]:.1f}" fill="none" stroke="#444" '
           f'stroke-width="1.3" stroke-dasharray="7,5" marker-end="url(#vee)"/>')
out.append('<rect x="766" y="950" width="68" height="17" fill="#fff" opacity="0.9"/>'
           '<text x="800" y="963" font-size="12" text-anchor="middle" fill="#444">«include»</text>')

# обобщение актёров
for child, parent in gens:
    cx, cy = actors[child][:2]
    px, py = actors[parent][:2]
    out.append(f'<line x1="{cx}" y1="{cy+92}" x2="{px}" y2="{py-58}" stroke="#222" stroke-width="1.4" marker-end="url(#tri)"/>')

# варианты использования
for uid, (x, y, text, uniq) in ucs.items():
    f, s = (UNIQ_F, UNIQ_S) if uniq else (BLUE_F, BLUE_S)
    sw = 2.4 if uniq else 1.5
    out.append(f'<ellipse cx="{x}" cy="{y}" rx="{RX}" ry="{RY}" fill="{f}" stroke="{s}" stroke-width="{sw}"/>')
    lines = [uid] + text.split("\n")
    y0 = y - (len(lines) - 1) * 7.5
    for i, ln in enumerate(lines):
        weight = ' font-weight="bold"' if i == 0 else ''
        out.append(f'<text x="{x}" y="{y0 + i*15 + 4}" font-size="{12 if i==0 else 13}" text-anchor="middle"{weight}>{ln}</text>')

# актёры
for aid, (x, y, label) in actors.items():
    out.append(f'<g stroke="#111" stroke-width="2.2" fill="none">'
               f'<circle cx="{x}" cy="{y-42}" r="13"/>'
               f'<line x1="{x}" y1="{y-29}" x2="{x}" y2="{y+14}"/>'
               f'<line x1="{x-26}" y1="{y-12}" x2="{x+26}" y2="{y-12}"/>'
               f'<line x1="{x}" y1="{y+14}" x2="{x-22}" y2="{y+50}"/>'
               f'<line x1="{x}" y1="{y+14}" x2="{x+22}" y2="{y+50}"/></g>')
    for i, ln in enumerate(label):
        out.append(f'<text x="{x}" y="{y+72+i*16}" font-size="14" text-anchor="middle">{ln}</text>')

# легенда
out.append('<g font-size="13">'
           f'<ellipse cx="330" cy="1295" rx="34" ry="13" fill="{UNIQ_F}" stroke="{UNIQ_S}" stroke-width="2.2"/>'
           '<text x="374" y="1300">— уникальный сервис PortaGraph (отсутствует у конкурентов)</text>'
           f'<ellipse cx="900" cy="1295" rx="34" ry="13" fill="{BLUE_F}" stroke="{BLUE_S}" stroke-width="1.5"/>'
           '<text x="944" y="1300">— базовый сервис</text></g>')
out.append('</svg>')
open("usecase.svg", "w").write("\n".join(out))
open("usecase.html", "w").write('<html><body style="margin:0">' + "\n".join(out) + "</body></html>")
