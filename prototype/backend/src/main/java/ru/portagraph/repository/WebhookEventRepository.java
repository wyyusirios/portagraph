package ru.portagraph.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.portagraph.domain.WebhookEvent;

public interface WebhookEventRepository extends JpaRepository<WebhookEvent, Long> {
    boolean existsByRepositoryIdAndDeliveryId(Long repositoryId, String deliveryId);
}
