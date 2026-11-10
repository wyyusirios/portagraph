package ru.portagraph.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.SecureRandom;
import java.util.Base64;

/** Шифрование токенов Git-хостингов алгоритмом AES-256-GCM. Ключ задаётся переменной окружения. */
@Component
public class CredentialCipher {

    private static final int IV_LENGTH = 12;
    private static final int TAG_BITS = 128;

    private final SecretKeySpec key;
    private final SecureRandom random = new SecureRandom();

    public CredentialCipher(@Value("${portagraph.security.credential-key}") String base64Key) {
        byte[] raw = Base64.getDecoder().decode(base64Key);
        if (raw.length != 32) {
            throw new IllegalStateException("Ключ шифрования должен быть 256 бит (32 байта в Base64)");
        }
        this.key = new SecretKeySpec(raw, "AES");
    }

    public byte[] encrypt(String token) {
        try {
            byte[] iv = new byte[IV_LENGTH];
            random.nextBytes(iv);
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.ENCRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
            byte[] enc = c.doFinal(token.getBytes(StandardCharsets.UTF_8));
            return ByteBuffer.allocate(iv.length + enc.length).put(iv).put(enc).array();
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("Не удалось зашифровать токен", e);
        }
    }

    public String decrypt(byte[] data) {
        try {
            ByteBuffer buf = ByteBuffer.wrap(data);
            byte[] iv = new byte[IV_LENGTH];
            buf.get(iv);
            byte[] enc = new byte[buf.remaining()];
            buf.get(enc);
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.DECRYPT_MODE, key, new GCMParameterSpec(TAG_BITS, iv));
            return new String(c.doFinal(enc), StandardCharsets.UTF_8);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("Не удалось расшифровать токен", e);
        }
    }
}
