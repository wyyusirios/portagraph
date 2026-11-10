package ru.shopflow.orders.service;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.shopflow.common.dto.Money;
import ru.shopflow.common.dto.OrderCreatedEvent;
import ru.shopflow.common.dto.UserDto;
import ru.shopflow.orders.client.AuthClient;
import ru.shopflow.orders.client.CatalogClient;
import ru.shopflow.orders.domain.Order;
import ru.shopflow.orders.events.OrderEventPublisher;
import ru.shopflow.orders.repository.OrderRepository;

import java.time.Instant;
import java.util.List;

@Service
public class OrderService {

    private final AuthClient auth;
    private final CatalogClient catalog;
    private final OrderRepository orders;
    private final PricingPolicy pricing;
    private final OrderEventPublisher events;

    public OrderService(AuthClient auth, CatalogClient catalog, OrderRepository orders,
                        PricingPolicy pricing, OrderEventPublisher events) {
        this.auth = auth;
        this.catalog = catalog;
        this.orders = orders;
        this.pricing = pricing;
        this.events = events;
    }

    @Transactional
    public Order create(long userId, List<OrderCreatedEvent.Line> lines) {
        UserDto user = auth.findUser(userId);
        lines.forEach(l -> catalog.reserve(l.sku(), l.quantity()));
        Money total = pricing.total(lines);
        Order order = orders.save(new Order(userId, total.amount()));
        events.publish(new OrderCreatedEvent(order.getId(), userId, user.email(), lines, total, Instant.now()));
        return order;
    }
}
