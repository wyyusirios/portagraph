package ru.shopflow.billing

import org.springframework.stereotype.Component
import org.springframework.web.client.RestClient
import ru.shopflow.common.dto.Money

/** Создание платежа во внешней платёжной системе. */
@Component
class YooKassaClient {
    private val http = RestClient.create("https://api.yookassa.ru/v3")

    fun createPayment(orderId: Long, amount: Money): String {
        val body = mapOf("amount" to mapOf("value" to amount.amount(), "currency" to amount.currency()),
                         "metadata" to mapOf("orderId" to orderId))
        val response = http.post().uri("/payments").body(body).retrieve().body(Map::class.java)
        return response?.get("id") as String
    }
}
