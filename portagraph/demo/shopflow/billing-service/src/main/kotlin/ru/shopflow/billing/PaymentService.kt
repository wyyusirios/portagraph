package ru.shopflow.billing

import org.springframework.kafka.annotation.KafkaListener
import org.springframework.kafka.core.KafkaTemplate
import org.springframework.stereotype.Service
import ru.shopflow.common.dto.OrderCreatedEvent
import ru.shopflow.common.dto.PaymentCompletedEvent
import java.time.Instant

@Service
class PaymentService(
    private val yooKassa: YooKassaClient,
    private val kafkaTemplate: KafkaTemplate<String, PaymentCompletedEvent>,
) {
    @KafkaListener(topics = ["orders.created"], groupId = "billing-service")
    fun onOrderCreated(event: OrderCreatedEvent) {
        val paymentId = yooKassa.createPayment(event.orderId(), event.total())
        kafkaTemplate.send("payments.completed", PaymentCompletedEvent(event.orderId(), paymentId, event.total(), Instant.now()))
    }
}
