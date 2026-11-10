package ru.shopflow.common.dto;

/** Пользователь в ответах auth-service. */
public record UserDto(long id, String email, String fullName, boolean blocked) {
}
