"""Шаблоны писем."""
from jinja2 import Template

ORDER_CREATED = Template("<h1>Заказ №{{ order_id }} оформлен</h1><p>Сумма: {{ total }} ₽</p>")
PAYMENT_DONE = Template("<h1>Оплата заказа №{{ order_id }} получена</h1>")


def render_order_created(event: dict) -> str:
    return ORDER_CREATED.render(order_id=event["orderId"], total=event["total"]["amount"])


def render_payment_done(event: dict) -> str:
    return PAYMENT_DONE.render(order_id=event["orderId"])
