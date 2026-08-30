/**
 * AURA RX Node - Offline CSI receiver (no router/internet).
 *
 * Promiscuous mode + CSI callback on fixed channel. Streams I/Q to host via UART
 * or processes edge vitals locally. Place around disaster perimeter.
 */
#include <string.h>
#include "esp_event.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"

#include "../../common/aura_protocol.h"
#include "csi_stream.h"

static const char *TAG = "aura_rx";

#ifndef CONFIG_AURA_NODE_ID
#define CONFIG_AURA_NODE_ID 1
#endif

static void wifi_csi_cb(void *ctx, wifi_csi_info_t *info)
{
    if (!info || !info->buf || info->len < 4) {
        return;
    }

    uint32_t ts = (uint32_t)(esp_timer_get_time() / 1000ULL);
    int8_t rssi = info->rx_ctrl.rssi;
    uint8_t ch = info->rx_ctrl.channel;

    csi_stream_on_frame((const int8_t *)info->buf, info->len, rssi, ch, ts);
}

static void wifi_promiscuous_cb(void *buf, wifi_promiscuous_pkt_type_t type)
{
    (void)buf;
    (void)type;
}

static void wifi_init_rx(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_ERROR_CHECK(esp_wifi_set_channel(AURA_WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));

    wifi_csi_config_t csi_config = {
        .lltf_en = true,
        .htltf_en = true,
        .stbc_htltf2_en = true,
        .ltf_merge_en = true,
        .channel_filter_en = false,
        .manu_scale = false,
    };
    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_config));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(wifi_csi_cb, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));

    ESP_ERROR_CHECK(esp_wifi_set_promiscuous(true));
    esp_wifi_set_promiscuous_rx_cb(wifi_promiscuous_cb);

    ESP_LOGI(TAG, "RX node %d listening on ch %d (offline CSI)", CONFIG_AURA_NODE_ID, AURA_WIFI_CHANNEL);
}

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    csi_stream_init(CONFIG_AURA_NODE_ID);
    wifi_init_rx();

    ESP_LOGI(TAG, "AURA RX active — connect USB-UART to record CSI");
    while (true) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}
