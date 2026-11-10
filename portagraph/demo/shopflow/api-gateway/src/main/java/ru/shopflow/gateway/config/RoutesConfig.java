package ru.shopflow.gateway.config;

import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RoutesConfig {

    @Bean
    RouteLocator routes(RouteLocatorBuilder builder) {
        return builder.routes()
                .route("auth", r -> r.path("/api/v1/auth/**").uri("http://auth-service:8080"))
                .route("catalog", r -> r.path("/api/v1/products/**").uri("http://catalog-service:8000"))
                .route("orders", r -> r.path("/api/v1/orders/**").uri("http://order-service:8080"))
                .build();
    }
}
