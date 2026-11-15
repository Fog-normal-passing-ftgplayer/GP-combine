// 宿主机仿真用的 esp_heap_caps 垫片：PSRAM 在这里就是普通堆。
#pragma once
#include <cstdlib>
#include <cstddef>
#include <cstdint>

#define MALLOC_CAP_EXEC     (1 << 0)
#define MALLOC_CAP_32BIT    (1 << 1)
#define MALLOC_CAP_8BIT     (1 << 2)
#define MALLOC_CAP_DMA      (1 << 3)
#define MALLOC_CAP_SPIRAM   (1 << 10)
#define MALLOC_CAP_INTERNAL (1 << 11)
#define MALLOC_CAP_DEFAULT  (1 << 12)

static inline void *heap_caps_malloc(size_t n, uint32_t) { return std::malloc(n); }
static inline void *heap_caps_calloc(size_t c, size_t n, uint32_t) { return std::calloc(c, n); }
static inline void *heap_caps_realloc(void *p, size_t n, uint32_t) { return std::realloc(p, n); }
static inline void heap_caps_free(void *p) { std::free(p); }
static inline size_t heap_caps_get_free_size(uint32_t) { return (size_t)8 << 20; }
static inline size_t heap_caps_get_largest_free_block(uint32_t) { return (size_t)4 << 20; }
