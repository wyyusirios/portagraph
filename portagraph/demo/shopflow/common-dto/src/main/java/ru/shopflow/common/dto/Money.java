package ru.shopflow.common.dto;

import java.math.BigDecimal;

/** Денежная сумма в рублях с точностью до копеек. */
public record Money(BigDecimal amount, String currency) {
    public static Money rub(long kopecks) {
        return new Money(BigDecimal.valueOf(kopecks, 2), "RUB");
    }

    public Money plus(Money other) {
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException("Разные валюты");
        }
        return new Money(amount.add(other.amount), currency);
    }
}
