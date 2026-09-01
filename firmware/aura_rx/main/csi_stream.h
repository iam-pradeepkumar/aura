#pragma once

#include <stddef.h>
#include <stdint.h>

#include "esp_netif.h"

void csi_stream_init(uint8_t node_id);
void csi_stream_open_udp(void);
void csi_stream_open_udp_gateway(esp_ip4_addr_t gw);
void csi_stream_wifi_connect(void);
void csi_stream_on_frame(const int8_t *iq, size_t len, int8_t rssi, uint8_t channel, uint32_t ts_ms);
