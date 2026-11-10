package ru.shopflow.orders.events;

import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;
import ru.shopflow.common.dto.OrderCreatedEvent;

@Component
public class OrderEventPublisher {

    public static final String TOPIC = "orders.created";

    private final KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate;

    public OrderEventPublisher(KafkaTemplate<String, OrderCreatedEvent> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void publish(OrderCreatedEvent event) {
        kafkaTemplate.send(TOPIC, String.valueOf(event.orderId()), event);
    }
}
