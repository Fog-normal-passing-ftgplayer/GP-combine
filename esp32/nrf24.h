#pragma once
#include <SPI.h>

// Minimal nRF24L01+ driver: fixed channel/address, 2Mbps, auto-ACK,
// static 15-byte payload. Register-level, no external library.

#define NRF24_PAYLOAD 15
#define NRF24_CHANNEL 120 // 2.500 GHz, above the WiFi band

class NRF24 {
public:
  void begin(SPIClass &spi, int csn, int ce) {
    _spi = &spi; _csn = csn; _ce = ce;
    pinMode(_csn, OUTPUT); digitalWrite(_csn, HIGH);
    pinMode(_ce, OUTPUT); digitalWrite(_ce, LOW);
    delay(10);
    writeReg(0x00, 0x00);            // power down
    writeReg(0x01, 0x3F);            // EN_AA: auto-ack all pipes
    writeReg(0x02, 0x03);            // EN_RXADDR: pipe0 + pipe1
    writeReg(0x03, 0x03);            // SETUP_AW: 5-byte addresses
    writeReg(0x04, 0x15);            // SETUP_RETR: 250us, 5 retries
    writeReg(0x05, NRF24_CHANNEL);   // RF_CH
    writeReg(0x06, 0x0E);            // RF_SETUP: 2Mbps, 0dBm
    static const uint8_t addr[5] = {0x46, 0x55, 0x53, 0x49, 0x4F}; // "FUSIO"
    writeReg(0x10, addr, 5);         // TX_ADDR
    writeReg(0x0A, addr, 5);         // RX_ADDR_P0 (auto-ack pipe)
    writeReg(0x0B, addr, 5);         // RX_ADDR_P1
    writeReg(0x11, NRF24_PAYLOAD);   // RX_PW_P0
    writeReg(0x12, NRF24_PAYLOAD);   // RX_PW_P1
    writeReg(0x07, 0x70);            // clear STATUS
  }

  // TX with auto-ACK; blocks up to ~2ms; true = ACK received
  bool writePacket(const uint8_t *data) {
    powerUpTx();
    writeReg(0x07, 0x70); // clear STATUS
    _spi->beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
    csLow(); _spi->transfer(0xA0); // W_TX_PAYLOAD
    for (int i = 0; i < NRF24_PAYLOAD; i++) _spi->transfer(data[i]);
    csHigh(); _spi->endTransaction();
    digitalWrite(_ce, HIGH); delayMicroseconds(12); digitalWrite(_ce, LOW);
    unsigned long t = micros();
    while (micros() - t < 2000) {
      uint8_t st = readReg(0x07);
      if (st & 0x20) { writeReg(0x07, 0x20); return true; }  // TX_DS
      if (st & 0x10) { writeReg(0x07, 0x10); flushTx(); return false; } // MAX_RT
    }
    return false;
  }

  bool readPacket(uint8_t *data) {
    uint8_t st = readReg(0x07);
    if (!(st & 0x40)) return false; // no RX_DR
    writeReg(0x07, 0x40);
    _spi->beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
    csLow(); _spi->transfer(0x61); // R_RX_PAYLOAD
    for (int i = 0; i < NRF24_PAYLOAD; i++) data[i] = _spi->transfer(0);
    csHigh(); _spi->endTransaction();
    return true;
  }

  void startListening() {
    writeReg(0x00, 0x03); // PWR_UP | PRIM_RX
    digitalWrite(_ce, HIGH);
    delayMicroseconds(130);
  }

  void powerUpTx() {
    writeReg(0x00, 0x02); // PWR_UP, PRIM_RX=0
    digitalWrite(_ce, LOW);
    delayMicroseconds(130);
  }

  void setChannel(uint8_t ch) { writeReg(0x05, ch); }

  // rate2M: true = 2Mbps, false = 1Mbps; pwrCode: 0=-18, 1=-12, 2=-6, 3=0 dBm
  void setRfConfig(bool rate2M, uint8_t pwrCode) {
    writeReg(0x06, (rate2M ? 0x08 : 0x00) | ((pwrCode & 0x03) << 1));
  }

  void powerUp() { writeReg(0x00, 0x02); }
  void powerDown() { writeReg(0x00, 0x00); }

  void resetLink() {
    flushTx();
    writeReg(0x07, 0x70); // clear STATUS
  }

private:
  SPIClass *_spi;
  int _csn, _ce;
  void csLow() { digitalWrite(_csn, LOW); }
  void csHigh() { digitalWrite(_csn, HIGH); }
  void writeReg(uint8_t reg, uint8_t val) {
    _spi->beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
    csLow(); _spi->transfer(0x20 | reg); _spi->transfer(val); csHigh();
    _spi->endTransaction();
  }
  void writeReg(uint8_t reg, const uint8_t *data, uint8_t len) {
    _spi->beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
    csLow(); _spi->transfer(0x20 | reg);
    for (uint8_t i = 0; i < len; i++) _spi->transfer(data[i]);
    csHigh(); _spi->endTransaction();
  }
  uint8_t readReg(uint8_t reg) {
    uint8_t v;
    _spi->beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
    csLow(); _spi->transfer(reg); v = _spi->transfer(0); csHigh();
    _spi->endTransaction();
    return v;
  }
  void flushTx() {
    _spi->beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
    csLow(); _spi->transfer(0xE1); csHigh(); _spi->endTransaction();
  }
};
