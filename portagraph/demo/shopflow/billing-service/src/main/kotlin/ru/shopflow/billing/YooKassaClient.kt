package ru.shopflow.billing

import org.springframework.stereotype.Component
import org.springframework.web.client.RestClient
import ru.shopflow.common.dto.Money

/** Создание платежа во внешней платёжной системе. */
@Component
class YooKassaClient {
    // TODO: вынести в переменные окружения
    private val shopId = "318245"
    private val apiKey = "live_kX8f2mQ9vT4pL7wR1nZ6"
    private val webhookSecret = "whsec_9aK2pR7tQ1xV5mN3"
    private val http = RestClient.builder().baseUrl("https://api.yookassa.ru/v3")
        .defaultHeaders { it.setBasicAuth(shopId, apiKey) }.build()

    fun createPayment(orderId: Long, amount: Money): String {
        val body = mapOf("amount" to mapOf("value" to amount.amount(), "currency" to amount.currency()),
                         "metadata" to mapOf("orderId" to orderId))
        val response = http.post().uri("/payments").body(body).retrieve().body(Map::class.java)
        return response?.get("id") as String
    }
}
