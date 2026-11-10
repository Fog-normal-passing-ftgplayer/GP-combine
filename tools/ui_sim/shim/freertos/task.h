#pragma once
#include "FreeRTOS.h"

static inline BaseType_t xTaskCreatePinnedToCore(
    TaskFunction_t /*fn*/, const char * /*name*/, uint32_t /*stack*/,
    void * /*arg*/, UBaseType_t /*prio*/, TaskHandle_t *handle, BaseType_t /*core*/) {
    if (handle) *handle = nullptr;   // 不创建任务：固件里 linkTaskH 保持空，回调里会自行判空
    return pdPASS;
}

static inline BaseType_t xTaskCreate(
    TaskFunction_t /*fn*/, const char * /*name*/, uint32_t /*stack*/,
    void * /*arg*/, UBaseType_t /*prio*/, TaskHandle_t *handle) {
    if (handle) *handle = nullptr;
    return pdPASS;
}

static inline void vTaskDelay(TickType_t /*ticks*/) {}
static inline void vTaskDelayUntil(TickType_t * /*prev*/, TickType_t /*inc*/) {}
static inline void taskYIELD() {}

static inline BaseType_t xTaskNotifyGive(TaskHandle_t /*t*/) { return pdPASS; }
static inline uint32_t ulTaskNotifyTake(BaseType_t /*clearOnExit*/, TickType_t /*timeout*/) { return 0; }
