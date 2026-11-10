package ru.shopflow.orders.service;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PricingPolicyTest {
    @Test
    void appliesDiscountFromFiveItems() {
        assertEquals(0.05, new PricingPolicy().discountFor(5), 1e-9);
        assertEquals(0.0, new PricingPolicy().discountFor(4), 1e-9);
    }
}
