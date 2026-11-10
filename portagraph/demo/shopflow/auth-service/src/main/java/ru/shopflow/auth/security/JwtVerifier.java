package ru.shopflow.auth.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

/**
 * Выпуск и проверка JWT (HS256). Единственное место в системе, где проверяется подпись токена.
 */
@Component
public class JwtVerifier {

    private final byte[] key;

    public JwtVerifier(@Value("${jwt.signing-key}") String signingKey) {
        this.key = signingKey.getBytes(StandardCharsets.UTF_8);
    }

    public String issue(long userId, long ttlSeconds) {
        String header = b64("{\"alg\":\"HS256\",\"typ\":\"JWT\"}");
        long exp = System.currentTimeMillis() / 1000 + ttlSeconds;
        String payload = b64("{\"sub\":\"" + userId + "\",\"exp\":" + exp + "}");
        return header + "." + payload + "." + sign(header + "." + payload);
    }

    public boolean verify(String token) {
        String[] parts = token.split("\\.");
        if (parts.length != 3) {
            return false;
        }
        return sign(parts[0] + "." + parts[1]).equals(parts[2]);
    }

    private String sign(String data) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return Base64.getUrlEncoder().withoutPadding().encodeToString(mac.doFinal(data.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) {
            throw new IllegalStateException("Не удалось подписать токен", e);
        }
    }

    private static String b64(String s) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(s.getBytes(StandardCharsets.UTF_8));
    }
}
