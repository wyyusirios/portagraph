package ru.shopflow.orders.client;

import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import ru.shopflow.common.dto.UserDto;

/** Получение данных пользователя из auth-service. */
@Component
public class AuthClient {

    private final RestClient http = RestClient.create("http://auth-service:8080/api/v1");

    public UserDto findUser(long userId) {
        UserDto user = http.get().uri("/users/{id}", userId).retrieve().body(UserDto.class);
        if (user == null || user.blocked()) {
            throw new IllegalStateException("Пользователь недоступен");
        }
        return user;
    }
}
