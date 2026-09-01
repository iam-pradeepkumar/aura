idf_component_register(SRCS "main.c" "csi_stream.c"
                    INCLUDE_DIRS "."
                    REQUIRES esp_wifi nvs_flash driver lwip esp_timer esp_event esp_netif)

# Set per-board ID:  AURA_NODE_ID=2 idf.py build flash
if(DEFINED ENV{AURA_NODE_ID})
    target_compile_definitions(${COMPONENT_LIB} PRIVATE CONFIG_AURA_NODE_ID=$ENV{AURA_NODE_ID})
endif()
