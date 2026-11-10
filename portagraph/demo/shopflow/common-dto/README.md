# common-dto

Общие DTO и контракты событий ShopFlow. Подключается сервисами заказов, оплаты и пользователей как Maven-зависимость, чтобы формат событий Kafka был единым.

## Содержимое
- `OrderCreatedEvent` — событие о новом заказе (топик `orders.created`)
- `PaymentCompletedEvent` — событие об успешной оплате (топик `payments.completed`)
- `UserDto`, `Money`
