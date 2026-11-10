package ru.portagraph.service;

/** Запрошенный объект не найден. */
public class NotFoundException extends RuntimeException {
    public NotFoundException(String message) {
        super(message);
    }
}
