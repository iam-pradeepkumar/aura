idf_component_register(SRCS "main.c" "csi_stream.c"
                    INCLUDE_DIRS "."
                    REQUIRES esp_wifi nvs_flash driver lwip esp_timer esp_event esp_netif)

# Per-board ID:  AURA_NODE_ID=2 idf.py build flash
# Use AURA_RX_NODE_ID (not CONFIG_AURA_NODE_ID — Kconfig always defaults to 1).
if(DEFINED ENV{AURA_NODE_ID} AND NOT "$ENV{AURA_NODE_ID}" STREQUAL "")
    set(_aura_rx_node_id "$ENV{AURA_NODE_ID}")
else()
    set(_aura_rx_node_id "1")
endif()
target_compile_definitions(${COMPONENT_LIB} PRIVATE AURA_RX_NODE_ID=${_aura_rx_node_id})
message(STATUS "AURA RX node ID for this build: ${_aura_rx_node_id}")
