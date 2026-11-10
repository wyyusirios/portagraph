package ru.shopflow.auth.security;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class JwtVerifierTest {
    @Test
    void rejectsTamperedToken() {
        JwtVerifier jwt = new JwtVerifier("test-key-test-key-test-key-test-key");
        String token = jwt.issue(42L, "USER");
        assertTrue(jwt.verify(token).isPresent());
        assertTrue(jwt.verify(token + "x").isEmpty());
    }
}
