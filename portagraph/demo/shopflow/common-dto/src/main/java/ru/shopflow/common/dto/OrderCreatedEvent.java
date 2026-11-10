package ru.shopflow.common.dto;

import java.time.Instant;
import java.util.List;

/** Публикуется order-service в топик orders.created после оформления заказа. */
public record OrderCreatedEvent(long orderId, long userId, String email, List<Line> lines, Money total, Instant createdAt) {
    public record Line(String sku, int quantity, Money price) {
    }
}
