package ru.shopflow.auth.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import ru.shopflow.auth.domain.User;

import java.util.Optional;

public interface UserRepository extends JpaRepository<User, Long> {
    Optional<User> findByEmailIgnoreCase(String email);
}
