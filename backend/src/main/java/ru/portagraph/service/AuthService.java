package ru.portagraph.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.jose.jws.MacAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import ru.portagraph.domain.User;
import ru.portagraph.repository.UserRepository;

import java.time.Duration;
import java.time.Instant;

/** Регистрация и вход; выдаёт JWT, в котором subject — идентификатор пользователя. */
@Service
public class AuthService {

    private final UserRepository users;
    private final PasswordEncoder encoder;
    private final JwtEncoder jwt;
    private final Duration ttl;

    public AuthService(UserRepository users, PasswordEncoder encoder, JwtEncoder jwt,
                       @Value("${portagraph.security.token-ttl:PT8H}") Duration ttl) {
        this.users = users;
        this.encoder = encoder;
        this.jwt = jwt;
        this.ttl = ttl;
    }

    public record Token(String value, long expiresIn) { }

    @Transactional
    public Token register(String email, String password, String fullName) {
        if (users.existsByEmailIgnoreCase(email)) {
            throw new IllegalArgumentException("Пользователь с таким email уже зарегистрирован");
        }
        User u = users.save(new User(email.strip().toLowerCase(), encoder.encode(password), fullName.strip()));
        return issue(u);
    }

    @Transactional(readOnly = true)
    public Token login(String email, String password) {
        User u = users.findByEmailIgnoreCase(email.strip())
                .filter(x -> encoder.matches(password, x.getPasswordHash()))
                .orElseThrow(() -> new BadCredentialsException("Неверный email или пароль"));
        return issue(u);
    }

    private Token issue(User u) {
        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuer("portagraph")
                .subject(String.valueOf(u.getId()))
                .issuedAt(now)
                .expiresAt(now.plus(ttl))
                .claim("name", u.getFullName())
                .build();
        String value = jwt.encode(JwtEncoderParameters.from(JwsHeader.with(MacAlgorithm.HS256).build(), claims))
                .getTokenValue();
        return new Token(value, ttl.toSeconds());
    }
}
