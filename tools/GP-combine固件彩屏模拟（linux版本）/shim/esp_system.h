// 宿主机仿真的 esp_system.h 垫片：只提供 esp_reset_reason()。
// 用环境变量 SIM_RESET_REASON 可以伪造复位原因，方便验证开机画面上的 RST 行
// （例如 SIM_RESET_REASON=BROWNOUT 会显示红色的 RST:BROWNOUT）。
#pragma once
#include <cstdlib>
#include <cstring>

typedef enum {
    ESP_RST_UNKNOWN = 0,
    ESP_RST_POWERON = 1,
    ESP_RST_EXT = 2,
    ESP_RST_SW = 3,
    ESP_RST_PANIC = 4,
    ESP_RST_INT_WDT = 5,
    ESP_RST_TASK_WDT = 6,
    ESP_RST_WDT = 7,
    ESP_RST_DEEPSLEEP = 8,
    ESP_RST_BROWNOUT = 9,
    ESP_RST_SDIO = 10,
} esp_reset_reason_t;

static inline esp_reset_reason_t esp_reset_reason(void) {
    const char *s = std::getenv("SIM_RESET_REASON");
    if (!s || !*s) return ESP_RST_POWERON;
    if (!std::strcmp(s, "BROWNOUT"))  return ESP_RST_BROWNOUT;
    if (!std::strcmp(s, "PANIC"))     return ESP_RST_PANIC;
    if (!std::strcmp(s, "TASK_WDT"))  return ESP_RST_TASK_WDT;
    if (!std::strcmp(s, "INT_WDT"))   return ESP_RST_INT_WDT;
    if (!std::strcmp(s, "WDT"))       return ESP_RST_WDT;
    if (!std::strcmp(s, "SW"))        return ESP_RST_SW;
    if (!std::strcmp(s, "DEEPSLEEP")) return ESP_RST_DEEPSLEEP;
    if (!std::strcmp(s, "EXT"))       return ESP_RST_EXT;
    return ESP_RST_UNKNOWN;
}
