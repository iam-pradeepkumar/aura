/**
 * AURA - Adaptive Urban Rescue Array
 * Shared protocol definitions for offline ESP32 CSI mesh (no internet/router).
 */
#pragma once

#include <stdint.h>

#define AURA_MAGIC 0x41555241u /* "AURA" */
#define AURA_VERSION 1
#define AURA_WIFI_CHANNEL 6
#define AURA_PROBE_INTERVAL_MS 50 /* ~20 Hz CSI sampling */

/* Local laptop hub — nodes join this WiFi hotspot (no internet) for wireless CSI upload */
#define AURA_HUB_SSID "AURA_HUB"
#define AURA_HUB_PASS "aura2026"
#define AURA_HUB_IP "192.168.4.1"
#define AURA_UDP_PORT 5555

/* CSI frame header streamed over UART / UDP */
typedef struct __attribute__((packed)) {
    uint32_t magic;
    uint8_t version;
    uint8_t node_id;
    uint8_t link_id;
    uint8_t reserved;
    uint32_t timestamp_ms;
    int8_t rssi;
    uint8_t channel;
    uint16_t subcarrier_count;
    uint16_t payload_bytes;
} aura_csi_header_t;

typedef struct __attribute__((packed)) {
    uint32_t magic;
    uint8_t node_id;
    uint8_t target_count;
    uint8_t motion_detected;
    uint8_t flags;
    float respiration_bpm;
    float heartbeat_bpm;
    float target_x_m;
    float target_y_m;
    float velocity_mps;
} aura_vitals_packet_t;

#define AURA_VITALS_MAGIC 0xC511AURAu
