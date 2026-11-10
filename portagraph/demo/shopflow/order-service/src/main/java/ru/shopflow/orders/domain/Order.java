package ru.shopflow.orders.domain;

import jakarta.persistence.*;

import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "orders")
public class Order {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    private Long userId;
    private BigDecimal total;
    @Enumerated(EnumType.STRING)
    private OrderStatus status = OrderStatus.NEW;
    private Instant createdAt = Instant.now();

    public Order() {
    }

    public Order(Long userId, BigDecimal total) {
        this.userId = userId;
        this.total = total;
    }

    public Long getId() { return id; }
    public Long getUserId() { return userId; }
    public BigDecimal getTotal() { return total; }
    public OrderStatus getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }

    public void markPaid() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException("Заказ уже обработан");
        }
        status = OrderStatus.PAID;
    }
}
