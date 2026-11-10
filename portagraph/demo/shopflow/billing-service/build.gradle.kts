plugins {
    id("org.springframework.boot") version "3.3.5"
    kotlin("jvm") version "2.0.20"
    kotlin("plugin.spring") version "2.0.20"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.kafka:spring-kafka")
    implementation("org.springframework.boot:spring-boot-starter-data-jdbc")
    implementation("ru.shopflow:common-dto:1.4.0")
    runtimeOnly("org.postgresql:postgresql")
}
