# order-service

Оформление заказов и управление их жизненным циклом. Проверяет пользователя в auth-service, резервирует товар в catalog-service, сохраняет заказ в orders-db и публикует событие `orders.created`. Получает подтверждение оплаты из топика `payments.completed`.
