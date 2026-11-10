package ru.shopflow.auth.web;

import org.springframework.web.bind.annotation.*;
import ru.shopflow.auth.security.JwtVerifier;
import ru.shopflow.auth.service.UserService;
import ru.shopflow.common.dto.UserDto;

import java.util.Map;

@RestController
@RequestMapping("/api/v1")
public class AuthController {

    private final UserService users;
    private final JwtVerifier jwt;

    public AuthController(UserService users, JwtVerifier jwt) {
        this.users = users;
        this.jwt = jwt;
    }

    @PostMapping("/auth/login")
    public Map<String, String> login(@RequestBody Map<String, String> body) {
        return Map.of("token", users.login(body.get("email"), body.get("password")));
    }

    @GetMapping("/users/{id}")
    public UserDto user(@PathVariable long id) {
        return users.find(id);
    }

    @PostMapping("/token/introspect")
    public Map<String, Boolean> introspect(@RequestBody Map<String, String> body) {
        return Map.of("active", jwt.verify(body.get("token")));
    }
}
