package ru.shopflow.auth.service;

import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import ru.shopflow.auth.domain.User;
import ru.shopflow.auth.repository.UserRepository;
import ru.shopflow.auth.security.JwtVerifier;
import ru.shopflow.common.dto.UserDto;

@Service
public class UserService {

    private final UserRepository users;
    private final JwtVerifier jwt;
    private final BCryptPasswordEncoder encoder = new BCryptPasswordEncoder();

    public UserService(UserRepository users, JwtVerifier jwt) {
        this.users = users;
        this.jwt = jwt;
    }

    public String login(String email, String password) {
        User u = users.findByEmailIgnoreCase(email)
                .filter(x -> !x.isBlocked() && encoder.matches(password, x.getPasswordHash()))
                .orElseThrow(() -> new IllegalArgumentException("Неверный email или пароль"));
        return jwt.issue(u.getId(), 3600);
    }

    public UserDto find(long id) {
        User u = users.findById(id).orElseThrow();
        return new UserDto(u.getId(), u.getEmail(), u.getFullName(), u.isBlocked());
    }
}
