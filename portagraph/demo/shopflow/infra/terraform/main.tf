terraform {
  required_providers {
    yandex = { source = "yandex-cloud/yandex" }
  }
}

resource "yandex_mdb_postgresql_cluster" "shopflow" {
  name        = "shopflow-pg"
  environment = "PRODUCTION"
  network_id  = var.network_id
}

resource "yandex_mdb_kafka_cluster" "events" {
  name       = "shopflow-kafka"
  network_id = var.network_id
}
