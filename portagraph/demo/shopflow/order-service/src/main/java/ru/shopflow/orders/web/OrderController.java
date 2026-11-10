package ru.shopflow.orders.web;

import org.springframework.web.bind.annotation.*;
import ru.shopflow.common.dto.OrderCreatedEvent;
import ru.shopflow.orders.domain.Order;
import ru.shopflow.orders.repository.OrderRepository;
import ru.shopflow.orders.service.OrderService;

import java.util.List;

@RestController
@RequestMapping("/api/v1/orders")
public class OrderController {

    private final OrderService service;
    private final OrderRepository orders;

    public OrderController(OrderService service, OrderRepository orders) {
        this.service = service;
        this.orders = orders;
    }

    @PostMapping
    public Order create(@RequestHeader("X-User-Id") long userId, @RequestBody List<OrderCreatedEvent.Line> lines) {
        return service.create(userId, lines);
    }

    @GetMapping("/{id}")
    public Order get(@PathVariable long id) {
        return orders.findById(id).orElseThrow();
    }
}
