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

/* CSI frame header streamed over UART / SD card */
typedef struct __attribute__((packed)) {
    uint32_t magic;
    uint8_t version;
    uint8_t node_id;
    uint8_t link_id; /* TX-RX pair identifier */
    uint8_t reserved;
    uint32_t timestamp_ms;
    int8_t rssi;
    uint8_t channel;
    uint16_t subcarrier_count;
    uint16_t payload_bytes; /* I/Q pairs: 2 bytes per subcarrier */
} aura_csi_header_t;

/* ESP-NOW vitals summary broadcast between nodes (no cloud) */
typedef struct __attribute__((packed)) {
    uint32_t magic; /* 0xC511AURA */
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
