#pragma once

#include <stdint.h>
#include <stddef.h>

void csi_stream_init(uint8_t node_id);
void csi_stream_on_frame(const int8_t *iq, size_t len, int8_t rssi, uint8_t channel, uint32_t ts_ms);
