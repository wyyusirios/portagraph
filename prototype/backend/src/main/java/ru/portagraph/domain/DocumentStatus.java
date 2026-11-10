package ru.portagraph.domain;

/** Статус документа: AI-черновик, подтверждён человеком или устарел после изменений. */
public enum DocumentStatus {
    DRAFT, APPROVED, OUTDATED
}
