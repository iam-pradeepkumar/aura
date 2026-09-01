idf_component_register(SRCS "main.c" "csi_stream.c"
                    INCLUDE_DIRS "."
                    REQUIRES esp_wifi nvs_flash driver lwip esp_timer esp_event esp_netif)
