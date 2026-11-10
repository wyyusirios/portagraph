package ru.shopflow.orders.client;

import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** Резервирование товара в catalog-service. */
@Component
public class CatalogClient {

    private final RestClient http = RestClient.create("http://catalog-service:8000/api/v1/products");

    public void reserve(String sku, int quantity) {
        http.post().uri("/{sku}/reserve?quantity={q}", sku, quantity).retrieve().toBodilessEntity();
    }
}
