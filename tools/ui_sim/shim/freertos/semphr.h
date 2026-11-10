#pragma once
#include "FreeRTOS.h"

// 单核仿真，互斥量永远拿得到；返回非空句柄，让固件里 `if (radioMx)` 的路径照常执行。
static inline SemaphoreHandle_t xSemaphoreCreateMutex() {
    static int anchor;
    return (SemaphoreHandle_t)&anchor;
}

static inline SemaphoreHandle_t xSemaphoreCreateBinary() {
    static int anchor2;
    return (SemaphoreHandle_t)&anchor2;
}

static inline BaseType_t xSemaphoreTake(SemaphoreHandle_t /*h*/, TickType_t /*ticks*/) { return pdTRUE; }
static inline BaseType_t xSemaphoreGive(SemaphoreHandle_t /*h*/) { return pdTRUE; }
static inline void vSemaphoreDelete(SemaphoreHandle_t /*h*/) {}
