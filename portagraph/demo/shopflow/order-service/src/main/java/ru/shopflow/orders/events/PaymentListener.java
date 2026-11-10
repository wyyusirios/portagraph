package ru.shopflow.orders.events;

import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;
import ru.shopflow.common.dto.PaymentCompletedEvent;
import ru.shopflow.orders.repository.OrderRepository;

/** Отмечает заказ оплаченным, когда billing-service подтверждает платёж. */
@Component
public class PaymentListener {

    private final OrderRepository orders;

    public PaymentListener(OrderRepository orders) {
        this.orders = orders;
    }

    @KafkaListener(topics = "payments.completed", groupId = "order-service")
    public void onPayment(PaymentCompletedEvent event) {
        orders.findById(event.orderId()).ifPresent(order -> {
            order.markPaid();
            orders.save(order);
        });
    }
}
