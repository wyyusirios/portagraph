"""Раскадровки пути пользователя из готовых макетов экранов."""
import pathlib, textwrap
from PIL import Image, ImageDraw, ImageFont

D = pathlib.Path(__file__).resolve().parents[1]
F = "/usr/share/fonts/opentype/inter/"
f_title = ImageFont.truetype(F + "Inter-Bold.otf", 40)
f_sub = ImageFont.truetype(F + "Inter-Regular.otf", 24)
f_cap_b = ImageFont.truetype(F + "Inter-SemiBold.otf", 24)
f_cap = ImageFont.truetype(F + "Inter-Regular.otf", 21)
f_num = ImageFont.truetype(F + "Inter-Bold.otf", 26)

def board(name, title, persona, frames):
    FW, FH, GAP, PAD = 760, 475, 46, 60
    CAP = 150
    cols = 3
    rows = (len(frames) + cols - 1) // cols
    W = PAD * 2 + cols * FW + (cols - 1) * GAP
    H = 190 + rows * (FH + CAP + GAP)
    img = Image.new("RGB", (W, H), "#f5f7fb")
    d = ImageDraw.Draw(img)
    d.text((PAD, 50), title, font=f_title, fill="#1b2559")
    d.text((PAD, 108), persona, font=f_sub, fill="#55618f")
    for i, (shot, head, text) in enumerate(frames):
        r, c = divmod(i, cols)
        x = PAD + c * (FW + GAP)
        y = 190 + r * (FH + CAP + GAP)
        im = Image.open(D / f"{shot}.png").convert("RGB").resize((FW, FH), Image.LANCZOS)
        d.rounded_rectangle([x - 2, y - 2, x + FW + 2, y + FH + 2], 14, outline="#c5d0fa", width=3)
        img.paste(im, (x, y))
        d.ellipse([x - 22, y - 22, x + 26, y + 26], fill="#3b5bdb")
        d.text((x + 2, y + 2), str(i + 1), font=f_num, fill="white", anchor="mm")
        d.text((x, y + FH + 18), head, font=f_cap_b, fill="#1b2559")
        for j, line in enumerate(textwrap.wrap(text, 62)):
            d.text((x, y + FH + 54 + j * 28), line, font=f_cap, fill="#55618f")
        if c < cols - 1 and i < len(frames) - 1:
            ax = x + FW + 8
            ay = y + FH // 2
            d.polygon([(ax, ay - 14), (ax + 26, ay), (ax, ay + 14)], fill="#3b5bdb")
    img.save(D / f"{name}.png", optimize=True)

board("storyboard_owner",
      "Раскадровка 1. Первый запуск: техлид подключает систему",
      "Персона: Анастасия, техлид команды ShopFlow. Цель — за 15 минут получить карту системы из 9 репозиториев.",
      [("m01_projects", "Создаёт проект", "Нажимает «Новый проект» и вводит название. Роли сервисов указывать не нужно."),
       ("m02_connect", "Подключает 9 репозиториев", "Вставляет адреса и токен только на чтение. Система проверяет доступ и подсвечивает репозиторий без прав."),
       ("m03_progress", "Следит за анализом", "Видит этапы и журнал агента: какую роль и назначение получил каждый репозиторий."),
       ("m04_map", "Получает карту системы", "Через несколько минут открывается карта: сервисы, базы данных, очереди и внешние системы."),
       ("m04_map", "Подтверждает выводы AI", "Проверяет описание order-service и доказательство связи и нажимает «Подтвердить»."),
       ("m08_docs", "Утверждает онбординг", "Формирует онбординг-гайд по графу, проверяет его и утверждает для новых сотрудников.")])

board("storyboard_developer",
      "Раскадровка 2. Новый разработчик готовит изменение",
      "Персона: Максим, backend-разработчик, вторая неделя в проекте. Задача — добавить claim «tenant_id» в JWT и ничего не сломать.",
      [("m08_docs", "Читает онбординг", "Начинает с утверждённого гайда: как устроена система и с каких файлов читать."),
       ("m06_assistant", "Спрашивает AI-ассистента", "«Где проверяется JWT?» Получает ответ со ссылками на 4 файла в трёх репозиториях."),
       ("m05_graph", "Изучает код по ссылке", "Переходит к OrderService и AuthClient. Видит зависимости класса и подсвеченные строки."),
       ("m04_map", "Смотрит связи на карте", "Убеждается, что auth-service используют api-gateway и order-service."),
       ("m07_impact", "Оценивает влияние", "Impact analysis: риск HIGH, затронуто 5 компонентов. AI подсказывает порядок выката."),
       ("m07_impact", "Планирует задачу", "Добавляет в задачу проверку gateway и order-service и предупреждает команду фронтенда.")])
print("storyboards ok")
