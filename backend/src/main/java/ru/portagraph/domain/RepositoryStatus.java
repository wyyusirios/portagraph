package ru.portagraph.domain;

/** Состояние подключённого репозитория. */
public enum RepositoryStatus {
    CONNECTED, INDEXING, READY, ERROR, ACCESS_DENIED
}
