/**
 * Stream raw CSI frames over UART in AURA binary format for host processing.
 */
#include <string.h>
#include "csi_stream.h"
#include "driver/uart.h"
#include "esp_log.h"

#include "../../common/aura_protocol.h"

static const char *TAG = "csi_stream";
static uint8_t s_node_id = 1;

void csi_stream_init(uint8_t node_id)
{
    s_node_id = node_id;

    uart_config_t uart_config = {
        .baud_rate = 921600,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
    };
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, 4096, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE,
                                  UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    ESP_LOGI(TAG, "CSI UART stream ready (node %u, 921600 baud)", s_node_id);
}

void csi_stream_on_frame(const int8_t *iq, size_t len, int8_t rssi, uint8_t channel, uint32_t ts_ms)
{
    if (len == 0 || iq == NULL) {
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

    uart_write_bytes(UART_NUM_0, &hdr, sizeof(hdr));
    uart_write_bytes(UART_NUM_0, (const char *)iq, len);
}
