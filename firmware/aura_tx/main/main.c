/**
 * AURA TX — broadcast null data frames for CSI stimulation (channel 6, no AP).
 */
#include <string.h>
#include "esp_event.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs_flash.h"

#include "../../common/aura_protocol.h"

static const char *TAG = "aura_tx";

/* Minimal 802.11 QoS data frame template (broadcast DA) */
static uint8_t s_probe_frame[24] = {
    0x08, 0x01, 0x00, 0x00,                         /* QoS Data */
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,             /* DA broadcast */
    0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC,             /* SA (overwritten) */
    0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,             /* BSSID */
    0x00, 0x00,                                     /* Seq */
    0x00, 0x00,                                     /* QoS */
};

static void wifi_init_tx(void)
{
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());

    uint8_t mac[6];
    ESP_ERROR_CHECK(esp_wifi_get_mac(WIFI_IF_STA, mac));
    memcpy(s_probe_frame + 10, mac, 6);
    memcpy(s_probe_frame + 16, mac, 6);

    ESP_ERROR_CHECK(esp_wifi_set_channel(AURA_WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE));
    ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));

    ESP_LOGI(TAG, "TX ready ch=%d MAC=%02x:%02x:%02x:%02x:%02x:%02x",
             AURA_WIFI_CHANNEL, mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
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

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ESP_ERROR_CHECK(nvs_flash_init());
    }

    wifi_init_tx();
    xTaskCreate(probe_task, "aura_probe", 4096, NULL, 5, NULL);
    ESP_LOGI(TAG, "AURA offline CSI probe active — no router/internet required");
}
