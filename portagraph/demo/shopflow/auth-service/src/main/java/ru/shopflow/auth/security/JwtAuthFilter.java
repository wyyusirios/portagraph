package ru.shopflow.auth.security;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/** Проверяет заголовок Authorization: Bearer <JWT> на защищённых эндпоинтах. */
public class JwtAuthFilter extends OncePerRequestFilter {

    private final JwtVerifier verifier;

    public JwtAuthFilter(JwtVerifier verifier) {
        this.verifier = verifier;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        String header = request.getHeader("Authorization");
        if (header != null && header.startsWith("Bearer ") && !verifier.verify(header.substring(7))) {
            response.sendError(401, "Недействительный токен");
            return;
        }
        chain.doFilter(request, response);
    }
}
