idf_component_register(
    SRCS "main.cpp" "drivers.cpp" "hardware_smoke.cpp" "network.cpp" "device_protocol.cpp" "voice_vad.cpp" "audio_capture.cpp"
    INCLUDE_DIRS "."
    REQUIRES pixelpet_vad esp_lcd esp_driver_spi esp_driver_gpio esp_driver_i2s
    PRIV_REQUIRES esp_wifi esp_netif esp_event nvs_flash tcp_transport esp_timer esp_hw_support
)
