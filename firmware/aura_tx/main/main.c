/**
 * AURA TX — CSI probe transmitter.
 * Joins laptop hotspot (AURA_HUB) and transmits on the AP channel so RX nodes
 * capture CSI at full rate while connected to the same hotspot.
 */
#include <string.h>
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"

#include "../../common/aura_protocol.h"

static const char *TAG = "aura_tx";

/* Minimal 802.11 QoS data frame template (broadcast DA) */
static uint8_t s_probe_frame[24] = {
    0x08, 0x01, 0x00, 0x00,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC,
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
    0x00, 0x00,
    0x00, 0x00,
};

static TaskHandle_t s_probe_task = NULL;

static void tx_wifi_connect(void)
{
    wifi_config_t wifi_config = {0};
    strncpy((char *)wifi_config.sta.ssid, AURA_HUB_SSID, sizeof(wifi_config.sta.ssid));
    strncpy((char *)wifi_config.sta.password, AURA_HUB_PASS, sizeof(wifi_config.sta.password));
    wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_connect());
    ESP_LOGI(TAG, "Connecting to %s (match RX hotspot channel)", AURA_HUB_SSID);
}

static void probe_task(void *arg)
{
    while (true) {
        esp_err_t err = esp_wifi_80211_tx(WIFI_IF_STA, s_probe_frame, sizeof(s_probe_frame), false);
        if (err != ESP_OK) {
            ESP_LOGW(TAG, "802.11 tx err %d", err);
        }
        vTaskDelay(pdMS_TO_TICKS(AURA_PROBE_INTERVAL_MS));
    }
}

static void on_wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        tx_wifi_connect();
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "Hub disconnected — retrying...");
        if (s_probe_task) {
            vTaskDelete(s_probe_task);
            s_probe_task = NULL;
        }
        esp_wifi_connect();
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)data;
        uint8_t ch = 0;
        wifi_second_chan_t second = 0;
        ESP_ERROR_CHECK(esp_wifi_get_channel(&ch, &second));
        ESP_LOGI(TAG, "TX linked — IP: " IPSTR " | probing on AP channel %u",
                 IP2STR(&event->ip_info.ip), ch);
        if (s_probe_task == NULL) {
            xTaskCreate(probe_task, "aura_probe", 4096, NULL, 5, &s_probe_task);
            ESP_LOGI(TAG, "AURA probe active ~%d Hz on channel %u",
                     1000 / AURA_PROBE_INTERVAL_MS, ch);
        }
    }
}

static void wifi_init_tx(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &on_wifi_event, NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &on_wifi_event, NULL));

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA, mac));
    memcpy(s_probe_frame + 10, mac, 6);
    memcpy(s_probe_frame + 16, mac, 6);

    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    ESP_LOGI(TAG, "TX ready MAC=%02x:%02x:%02x:%02x:%02x:%02x",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
}

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    wifi_init_tx();
    ESP_LOGI(TAG, "AURA TX waiting for hotspot %s ...", AURA_HUB_SSID);
}
