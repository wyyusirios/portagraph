package ru.shopflow.gateway.filter;

import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.util.Map;

/** Проверяет токен у auth-service перед тем, как передать запрос дальше. */
@Component
public class TokenRelayFilter implements GlobalFilter {

    private final WebClient auth = WebClient.create("http://auth-service:8080/api/v1/token/introspect");

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        String header = exchange.getRequest().getHeaders().getFirst("Authorization");
        if (header == null || exchange.getRequest().getPath().value().startsWith("/api/v1/auth")) {
            return chain.filter(exchange);
        }
        return auth.post().bodyValue(Map.of("token", header.substring(7)))
                .retrieve().bodyToMono(Map.class)
                .flatMap(r -> Boolean.TRUE.equals(r.get("active")) ? chain.filter(exchange) : reject(exchange));
    }

    private Mono<Void> reject(ServerWebExchange exchange) {
        exchange.getResponse().setStatusCode(HttpStatus.UNAUTHORIZED);
        return exchange.getResponse().setComplete();
    }
}
