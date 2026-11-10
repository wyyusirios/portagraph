package ru.shopflow.common.dto;

import java.time.Instant;

/** Публикуется billing-service в топик payments.completed после подтверждения оплаты. */
public record PaymentCompletedEvent(long orderId, String paymentId, Money amount, Instant paidAt) {
}
