#pragma once
// 转发头：真正的驱动在 ../nrf24_common/nrf24_esp32.h，两份 ESP32 固件共用一份实现。
// 曾经这里各自演化出一份副本，导致「发送超时不清 TX FIFO」的修复只进了
// esp32_170x320，默认的 240x135 版一直在时连时断 —— 不要再往这里写实现。
#include "../nrf24_common/nrf24_esp32.h"
