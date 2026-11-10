#pragma once
#include "FreeRTOS.h"
#include <cstdlib>
#include <cstring>

// 一个够用的环形队列：M1 注入输入帧后，loop() 要靠它把帧取走。
struct SimQueue {
    uint8_t *buf = nullptr;
    size_t itemSize = 0;
    size_t cap = 0;
    size_t head = 0;
    size_t count = 0;
};

static inline QueueHandle_t xQueueCreate(UBaseType_t length, UBaseType_t itemSize) {
    if (length == 0 || itemSize == 0) return nullptr;
    SimQueue *q = (SimQueue *)std::calloc(1, sizeof(SimQueue));
    if (!q) return nullptr;
    q->buf = (uint8_t *)std::calloc((size_t)length, (size_t)itemSize);
    if (!q->buf) { std::free(q); return nullptr; }
    q->itemSize = (size_t)itemSize;
    q->cap = (size_t)length;
    return (QueueHandle_t)q;
}

static inline void vQueueDelete(QueueHandle_t h) {
    SimQueue *q = (SimQueue *)h;
    if (!q) return;
    std::free(q->buf);
    std::free(q);
}

static inline BaseType_t xQueueSend(QueueHandle_t h, const void *item, TickType_t /*ticks*/) {
    SimQueue *q = (SimQueue *)h;
    if (!q || q->count >= q->cap) return pdFALSE;
    size_t slot = (q->head + q->count) % q->cap;
    std::memcpy(q->buf + slot * q->itemSize, item, q->itemSize);
    q->count++;
    return pdTRUE;
}

static inline BaseType_t xQueueReceive(QueueHandle_t h, void *out, TickType_t /*ticks*/) {
    SimQueue *q = (SimQueue *)h;
    if (!q || q->count == 0) return pdFALSE;
    std::memcpy(out, q->buf + q->head * q->itemSize, q->itemSize);
    q->head = (q->head + 1) % q->cap;
    q->count--;
    return pdTRUE;
}

static inline UBaseType_t uxQueueMessagesWaiting(QueueHandle_t h) {
    SimQueue *q = (SimQueue *)h;
    return q ? (UBaseType_t)q->count : 0;
}
