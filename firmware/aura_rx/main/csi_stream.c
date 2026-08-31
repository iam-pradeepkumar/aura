/**
 * Stream CSI over UART (optional) and WiFi UDP to laptop hub — no USB cable required.
 */
#include <string.h>
#include <sys/socket.h>
#include "csi_stream.h"
#include "driver/uart.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "lwip/sockets.h"
#include "lwip/netdb.h"

#include "../../common/aura_protocol.h"

static const char *TAG = "csi_stream";
static uint8_t s_node_id = 1;
static int s_udp_sock = -1;
static struct sockaddr_in s_hub_addr;

#ifndef CONFIG_AURA_USE_UART
#define CONFIG_AURA_USE_UART 0
#endif

static void uart_init_optional(void)
{
#if CONFIG_AURA_USE_UART
    uart_config_t uart_config = {
        .baud_rate = 921600,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
    };
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, 4096, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0, &uart_config));
    ESP_LOGI(TAG, "UART backup enabled");
#endif
}

void csi_stream_init(uint8_t node_id)
{
    s_node_id = node_id;
    uart_init_optional();

    s_udp_sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_IP);
    if (s_udp_sock < 0) {
        ESP_LOGE(TAG, "UDP socket failed");
        return;
    }

    s_hub_addr.sin_family = AF_INET;
    s_hub_addr.sin_port = htons(AURA_UDP_PORT);
    inet_pton(AF_INET, AURA_HUB_IP, &s_hub_addr.sin_addr);

    ESP_LOGI(TAG, "Wireless stream ready → %s:%d (node %u)", AURA_HUB_IP, AURA_UDP_PORT, s_node_id);
}

void csi_stream_wifi_connect(void)
{
    wifi_config_t wifi_config = {0};
    strncpy((char *)wifi_config.sta.ssid, AURA_HUB_SSID, sizeof(wifi_config.sta.ssid));
    strncpy((char *)wifi_config.sta.password, AURA_HUB_PASS, sizeof(wifi_config.sta.password));
    wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_connect());

    ESP_LOGI(TAG, "Connecting to laptop hub SSID=%s (local only, no internet)", AURA_HUB_SSID);
}

#define AURA_MAX_CSI_BYTES 512

void csi_stream_on_frame(const int8_t *iq, size_t len, int8_t rssi, uint8_t channel, uint32_t ts_ms)
{
    if (len == 0 || iq == NULL || len > AURA_MAX_CSI_BYTES) {
        return;
    }

    aura_csi_header_t hdr = {
        .magic = AURA_MAGIC,
        .version = AURA_VERSION,
        .node_id = s_node_id,
        .link_id = 0,
        .reserved = 0,
        .timestamp_ms = ts_ms,
        .rssi = rssi,
        .channel = channel,
        .subcarrier_count = (uint16_t)(len / 2),
        .payload_bytes = (uint16_t)len,
    };

    if (s_udp_sock >= 0) {
        uint8_t packet[sizeof(aura_csi_header_t) + AURA_MAX_CSI_BYTES];
        memcpy(packet, &hdr, sizeof(hdr));
        memcpy(packet + sizeof(hdr), iq, len);
        sendto(s_udp_sock, packet, sizeof(hdr) + len, 0,
               (struct sockaddr *)&s_hub_addr, sizeof(s_hub_addr));
    }

#if CONFIG_AURA_USE_UART
    uart_write_bytes(UART_NUM_0, &hdr, sizeof(hdr));
    uart_write_bytes(UART_NUM_0, (const char *)iq, len);
#endif
}
