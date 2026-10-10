#pragma once
// ---------------------------------------------------------------------------
// nRF24L01+ 驱动（ESP32 / Arduino 侧）—— esp32 与 esp32_170x320 两份固件共用
//
// 以前这里是两份各自演化的副本（esp32/nrf24.h 与 esp32_170x320/nrf24.h）。
// 结果「发送超时没清 TX FIFO」的修复只进了 170x320 一份，默认的 240x135 版
// 一直在时连时断。现在只有这一份真实实现，两个 sketch 目录里的 nrf24.h
// 只是转发头，不要再往那边写实现。
//
// 链路参数必须和接收端 headers/addons/nrf24.h 完全一致：
//   信道 / 地址 / 速率 / CRC / 载荷宽度 / EN_AA
// ---------------------------------------------------------------------------

#include <SPI.h>

// 信道/地址/速率/CRC/载荷/重传 全部来自这个共享文件 —— 接收端
// (headers/addons/nrf24.h) 和 tools/ 下的诊断程序包含的是同一份。
#include "nrf24_link_params.h"

// 轮询窗口必须大于最坏重传时序，否则会在 MAX_RT 置位之前就退出循环、把包留在
// TX FIFO 里。旧 esp32/nrf24.h 正是这样坏的：2000 µs 窗口 vs ≈1886 µs 的最坏
// 重传时序，只差 100 µs，边界上随机命中 -> 旧包排队 -> 时连时断。
// 用 static_assert 钉死：以后动 NRF24_ATTEMPTS / NRF24_ARD_US 也不会再失配。
static_assert(NRF24_TX_WINDOW_US > NRF24_MAXRT_US + 200,
              "TX polling window must exceed the worst-case retry sequence, "
              "otherwise MAX_RT is missed and packets silt up in the TX FIFO");

class NRF24 {
public:
  void begin(SPIClass &spi, int csn, int ce) {
    _spi = &spi; _csn = csn; _ce = ce;
    pinMode(_csn, OUTPUT); digitalWrite(_csn, HIGH);
    pinMode(_ce, OUTPUT); digitalWrite(_ce, LOW);
    delay(10);
    writeReg(0x00, 0x00);                   // power down
    writeReg(0x01, NRF24_REG_EN_AA);        // EN_AA: 仅 pipe0（auto-ack）
    writeReg(0x02, NRF24_REG_EN_RXADDR);    // EN_RXADDR: 仅 pipe0
    writeReg(0x03, NRF24_REG_SETUP_AW);     // SETUP_AW: 5-byte addresses
    writeReg(0x04, NRF24_REG_SETUP_RETR);   // SETUP_RETR: ARD=250us, ARC=3
    writeReg(0x05, NRF24_CHANNEL);          // RF_CH
    writeReg(0x06, NRF24_REG_RF_SETUP);     // RF_SETUP: 2Mbps, 0dBm
    static const uint8_t addr[5] = NRF24_ADDR_INIT;
    writeReg(0x10, addr, 5);                // TX_ADDR
    writeReg(0x0A, addr, 5);                // RX_ADDR_P0 (auto-ack pipe)
    writeReg(0x11, NRF24_PAYLOAD);          // RX_PW_P0
    writeReg(0x07, NRF24_REG_STATUS_CLR);   // clear STATUS
    writeReg(0x00, NRF24_REG_CONFIG_TX);    // PWR_UP + 2字节CRC
    flushTx();                       // 上一轮可能留下残包，上电不清干净会一路排队
    flushRx();
    delay(2);
  }

  // TX with auto-ACK。true = 收到 ACK（TX_DS）。
  // 最坏阻塞 ≈ NRF24_TX_WINDOW_US。**所有**失败路径都清 STATUS + flushTx：
  // nRF24 的载荷只有在 TX_DS / MAX_RT / FLUSH_TX 时才从 TX FIFO 弹出，漏掉
  // flushTx 旧包就会排队，接收端拿到的是过期输入；FIFO（3 格）满了以后
  // W_TX_PAYLOAD 会被静默丢弃，链路表现为周期性假死/重连。
  bool writePacket(const uint8_t *data) {
    writeReg(0x07, NRF24_REG_STATUS_CLR);   // clear STATUS
    _spi->beginTransaction(SPISettings(4000000, MSBFIRST, SPI_MODE0));
    csLow(); _spi->transfer(0xA0);   // W_TX_PAYLOAD
    for (int i = 0; i < NRF24_PAYLOAD; i++) _spi->transfer(data[i]);
    csHigh(); _spi->endTransaction();
    digitalWrite(_ce, HIGH); delayMicroseconds(20); digitalWrite(_ce, LOW);
    unsigned long t = micros();
    while (micros() - t < NRF24_TX_WINDOW_US) {
      uint8_t st = readReg(0x07);
      if (st & 0x20) { writeReg(0x07, 0x20); return true; }  // TX_DS
      if (st & 0x10) { resetLink(); return false; }          // MAX_RT
    }
    resetLink();   // 超时：射频可能还在重传，STATUS 与 TX FIFO 都要清干净
    return false;
  }

  bool readPacket(uint8_t *data) {
    uint8_t st = readReg(0x07);
    // RX_P_NO (bit3:1) = 0b111 表示 RX FIFO 空；只认 RX_DR 有可能读到空包
    if (!(st & 0x40) || (st & 0x0E) == 0x0E) return false;
    writeReg(0x07, 0x40);
    _spi->beginTransaction(SPISettings(4000000, MSBFIRST, SPI_MODE0));
    csLow(); _spi->transfer(0x61);   // R_RX_PAYLOAD
    for (int i = 0; i < NRF24_PAYLOAD; i++) data[i] = _spi->transfer(0);
    csHigh(); _spi->endTransaction();
    return true;
  }

  void startListening() {
    writeReg(0x00, NRF24_REG_CONFIG_RX); // PWR_UP | PRIM_RX | 2字节CRC
    digitalWrite(_ce, HIGH);
    delayMicroseconds(130);
  }

  void setChannel(uint8_t ch) { writeReg(0x05, ch); }

  void powerUp() { writeReg(0x00, NRF24_REG_CONFIG_TX); }
  void powerDown() { writeReg(0x00, 0x00); }

  // 清 STATUS（RX_DR/TX_DS/MAX_RT）+ 清 TX FIFO。菜单里的「重新配对」也用它。
  void resetLink() {
    writeReg(0x07, NRF24_REG_STATUS_CLR);
    flushTx();
  }

private:
  SPIClass *_spi;
  int _csn, _ce;
  void csLow() { digitalWrite(_csn, LOW); }
  void csHigh() { digitalWrite(_csn, HIGH); }
  void writeReg(uint8_t reg, uint8_t val) {
    _spi->beginTransaction(SPISettings(4000000, MSBFIRST, SPI_MODE0));
    csLow(); _spi->transfer(0x20 | reg); _spi->transfer(val); csHigh();
    _spi->endTransaction();
  }
  void writeReg(uint8_t reg, const uint8_t *data, uint8_t len) {
    _spi->beginTransaction(SPISettings(4000000, MSBFIRST, SPI_MODE0));
    csLow(); _spi->transfer(0x20 | reg);
    for (uint8_t i = 0; i < len; i++) _spi->transfer(data[i]);
    csHigh(); _spi->endTransaction();
  }
  uint8_t readReg(uint8_t reg) {
    uint8_t v;
    _spi->beginTransaction(SPISettings(4000000, MSBFIRST, SPI_MODE0));
    csLow(); _spi->transfer(reg); v = _spi->transfer(0); csHigh();
    _spi->endTransaction();
    return v;
  }
  void flushCmd(uint8_t cmd) {
    _spi->beginTransaction(SPISettings(4000000, MSBFIRST, SPI_MODE0));
    csLow(); _spi->transfer(cmd); csHigh(); _spi->endTransaction();
  }
  void flushTx() { flushCmd(0xE1); }   // FLUSH_TX
  void flushRx() { flushCmd(0xE2); }   // FLUSH_RX
};
