// 宿主机仿真用的 FreeRTOS 垫片：任务一律不创建，信号量/队列是"永远成功"的假句柄。
// 固件里 linkTask/radioTask 因此不会跑；输入由仿真器直接喂给 handleRxByte()。
#pragma once

#include <cstdint>
#include <cstddef>

typedef void *SemaphoreHandle_t;
typedef void *QueueHandle_t;
typedef void *TaskHandle_t;

typedef uint32_t TickType_t;
typedef uint32_t UBaseType_t;
typedef int32_t BaseType_t;
typedef uint32_t StackType_t;

typedef void (*TaskFunction_t)(void *);

#define pdTRUE 1
#define pdFALSE 0
#define pdPASS 1
#define pdFAIL 0
#define portMAX_DELAY ((TickType_t)0xffffffffUL)
#define portTICK_PERIOD_MS 1
#define pdMS_TO_TICKS(x) ((TickType_t)(x))

static inline void sim_touch(void *p) {
    // 让假句柄非空，避免固件里 `if (linkQ)` / `if (radioMx)` 走到空分支
    static int anchor;
    (void)p;
    (void)anchor;
}

#include "freertos/task.h"
#include "freertos/queue.h"
#include "freertos/semphr.h"
