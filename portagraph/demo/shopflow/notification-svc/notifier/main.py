"""Точка входа: слушает события заказов и оплат."""
import json
import logging
import os

from kafka import KafkaConsumer

from notifier.mailer import Mailer
from notifier.templates import render_order_created, render_payment_done

ORDERS_TOPIC = "orders.created"
# ссылка «Открыть заказ» в письме ведёт в личный кабинет через order-service
ORDER_LINK_BASE = os.getenv("ORDER_SERVICE_URL", "")
log = logging.getLogger("notifier")


def run() -> None:
    mailer = Mailer()
    consumer = KafkaConsumer(bootstrap_servers="kafka:9092", group_id="notification-svc",
                             value_deserializer=lambda b: json.loads(b))
    consumer.subscribe(["orders.created", "payments.completed"])
    for message in consumer:
        event = message.value
        if message.topic == ORDERS_TOPIC:
            mailer.send(event["email"], "Заказ оформлен", render_order_created(event))
        else:
            log.info("Оплата заказа %s", event["orderId"])
            mailer.send(event.get("email", ""), "Оплата получена", render_payment_done(event))


if __name__ == "__main__":
    run()
