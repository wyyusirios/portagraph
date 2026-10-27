package ru.portagraph.integration.git;

/** Нет доступа к репозиторию: неверный токен, недостаточно прав или репозиторий не найден. */
public class RepositoryAccessException extends RuntimeException {
    public RepositoryAccessException(String message) {
        super(message);
    }
}
