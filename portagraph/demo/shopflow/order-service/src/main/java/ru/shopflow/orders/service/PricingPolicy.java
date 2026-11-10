package ru.shopflow.orders.service;

import org.springframework.stereotype.Component;
import ru.shopflow.common.dto.Money;
import ru.shopflow.common.dto.OrderCreatedEvent;

import java.util.List;

/** Расчёт итоговой суммы заказа: скидка 5% от 10 000 ₽. */
@Component
public class PricingPolicy {

    public Money total(List<OrderCreatedEvent.Line> lines) {
        Money sum = Money.rub(0);
        for (OrderCreatedEvent.Line l : lines) {
            for (int i = 0; i < l.quantity(); i++) {
                sum = sum.plus(l.price());
            }
        }
        if (sum.amount().doubleValue() >= 10000) {
            return new Money(sum.amount().multiply(java.math.BigDecimal.valueOf(0.95)), sum.currency());
        }
        return sum;
    }
}
