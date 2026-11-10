// 宿主机仿真用的 SPI 垫片：只吞掉字节，什么也不做。
// 显示、nRF24 都走这里 —— 仿真时它们不产生任何外部副作用。
#pragma once

#include <cstdint>
#include <cstddef>

#define MSBFIRST 1
#define LSBFIRST 0

#define SPI_MODE0 0x00
#define SPI_MODE1 0x01
#define SPI_MODE2 0x02
#define SPI_MODE3 0x03

class SPISettings {
public:
    SPISettings() {}
    SPISettings(uint32_t clock, uint8_t bitOrder, uint8_t dataMode)
        : clock_(clock), bitOrder_(bitOrder), dataMode_(dataMode) {}
    uint32_t clock_ = 4000000;
    uint8_t bitOrder_ = MSBFIRST;
    uint8_t dataMode_ = SPI_MODE0;
};

class SPIClass {
public:
    explicit SPIClass(uint8_t /*bus*/ = 0) {}

    bool begin(int8_t /*sck*/ = -1, int8_t /*miso*/ = -1, int8_t /*mosi*/ = -1, int8_t /*ss*/ = -1) {
        return true;
    }
    bool end() { return true; }

    void setFrequency(uint32_t /*freq*/) {}

    // 关键：恒返回 0x20（STATUS 的 TX_DS 位）。
    // nRF24 驱动的 writePacket() 是 busy-wait 轮询 STATUS 等 TX_DS/MAX_RT，
    // 而仿真的假时钟只随 delay() 前进 —— 如果这里返回 0，那个 while 永远等不到
    // 条件成立，整个仿真会死循环。返回 TX_DS 等于告诉驱动"这一包 ACK 了"，
    // 轮询第一圈就退出。readPacket() 仍返回 false（没有 RX_DR），不会凭空造收包。
    uint8_t transfer(uint8_t /*data*/) { return 0x20; }
    void transfer(const void * /*buf*/, size_t /*count*/) {}

    void beginTransaction(SPISettings /*settings*/) {}
    void endTransaction() {}
};

extern SPIClass SPI;
