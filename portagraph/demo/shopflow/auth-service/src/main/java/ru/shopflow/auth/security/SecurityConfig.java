package ru.shopflow.auth.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http, JwtVerifier verifier) throws Exception {
        http.csrf(c -> c.disable())
            .authorizeHttpRequests(a -> a
                .requestMatchers("/api/v1/auth/**", "/api/v1/token/introspect").permitAll()
                .anyRequest().authenticated())
            .addFilterBefore(new JwtAuthFilter(verifier), org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }
}
