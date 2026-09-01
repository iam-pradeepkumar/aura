idf_component_register(SRCS "main.c" "csi_stream.c"
                    INCLUDE_DIRS "."
                    REQUIRES esp_wifi nvs_flash driver lwip esp_timer esp_event esp_netif)

# Node ID: env AURA_NODE_ID=2  OR  idf.py -D AURA_RX_NODE_ID=2
if(DEFINED ENV{AURA_NODE_ID} AND NOT "$ENV{AURA_NODE_ID}" STREQUAL "")
    set(_aura_node_req "$ENV{AURA_NODE_ID}")
elseif(DEFINED AURA_RX_NODE_ID)
    set(_aura_node_req "${AURA_RX_NODE_ID}")
else()
    set(_aura_node_req "1")
endif()

set(AURA_RX_NODE_ID "${_aura_node_req}" CACHE STRING "AURA RX node ID (1-4)" FORCE)
message(STATUS ">>> AURA RX NODE ID = ${AURA_RX_NODE_ID} <<<")

configure_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/aura_node_config.h.in"
    "${CMAKE_CURRENT_BINARY_DIR}/aura_node_config.h"
    @ONLY
)

target_include_directories(${COMPONENT_LIB} PUBLIC "${CMAKE_CURRENT_BINARY_DIR}")
target_compile_definitions(${COMPONENT_LIB} PRIVATE AURA_RX_NODE_ID=${AURA_RX_NODE_ID})
