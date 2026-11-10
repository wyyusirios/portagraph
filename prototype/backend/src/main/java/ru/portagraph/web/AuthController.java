package ru.portagraph.web;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import ru.portagraph.service.AuthService;
import ru.portagraph.web.dto.Dto.LoginRequest;
import ru.portagraph.web.dto.Dto.RegisterRequest;
import ru.portagraph.web.dto.Dto.TokenResponse;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    private final AuthService auth;

    public AuthController(AuthService auth) {
        this.auth = auth;
    }

    @PostMapping("/register")
    @ResponseStatus(HttpStatus.CREATED)
    public TokenResponse register(@Valid @RequestBody RegisterRequest r) {
        AuthService.Token t = auth.register(r.email(), r.password(), r.fullName());
        return new TokenResponse(t.value(), t.expiresIn());
    }

    @PostMapping("/login")
    public TokenResponse login(@Valid @RequestBody LoginRequest r) {
        AuthService.Token t = auth.login(r.email(), r.password());
        return new TokenResponse(t.value(), t.expiresIn());
    }
}
