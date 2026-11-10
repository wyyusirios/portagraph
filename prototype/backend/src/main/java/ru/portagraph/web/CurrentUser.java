package ru.portagraph.web;

import org.springframework.security.oauth2.jwt.Jwt;

/** Идентификатор пользователя из JWT (subject). */
final class CurrentUser {
    private CurrentUser() { }

    static Long id(Jwt jwt) {
        return Long.valueOf(jwt.getSubject());
    }
}
