package ru.shopflow.orders.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.shopflow.orders.domain.Order;

public interface OrderRepository extends JpaRepository<Order, Long> {
}
