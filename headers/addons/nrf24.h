#ifndef _NRF24_PICO_H_
#define _NRF24_PICO_H_

// Minimal nRF24L01+ driver for RP2040 (pico-sdk): fixed channel/address,
// 2Mbps, auto-ACK, static 15-byte payload.

#include "hardware/spi.h"
#include "hardware/gpio.h"
#include "pico/time.h"
#include <stdint.h>
#include <string.h>

#define NRF24_PAYLOAD 15
#define NRF24_CHANNEL 120 // 2.500 GHz, above the WiFi band

class NRF24 {
public:
  void begin(spi_inst_t *spi, uint csn, uint ce) {
    _spi = spi; _csn = csn; _ce = ce;
    gpio_init(_csn); gpio_set_dir(_csn, GPIO_OUT); gpio_put(_csn, 1);
    gpio_init(_ce); gpio_set_dir(_ce, GPIO_OUT); gpio_put(_ce, 0);
    spi_init(_spi, 8000000);
    spi_set_format(_spi, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
    sleep_ms(10);
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

  bool writePacket(const uint8_t *data) {
    powerUpTx();
    writeReg(0x07, 0x70);
    gpio_put(_csn, 0);
    uint8_t cmd = 0xA0; // W_TX_PAYLOAD
    spi_write_blocking(_spi, &cmd, 1);
    spi_write_blocking(_spi, data, NRF24_PAYLOAD);
    gpio_put(_csn, 1);
    gpio_put(_ce, 1); busy_wait_us(12); gpio_put(_ce, 0);
    absolute_time_t until = make_timeout_time_ms(2);
    while (!time_reached(until)) {
      uint8_t st = readReg(0x07);
      if (st & 0x20) { writeReg(0x07, 0x20); return true; }  // TX_DS
      if (st & 0x10) { writeReg(0x07, 0x10); flushTx(); return false; } // MAX_RT
    }
    return false;
  }

  bool readPacket(uint8_t *data) {
    uint8_t st = readReg(0x07);
    if (!(st & 0x40)) return false;
    writeReg(0x07, 0x40);
    gpio_put(_csn, 0);
    uint8_t cmd = 0x61; // R_RX_PAYLOAD
    spi_write_blocking(_spi, &cmd, 1);
    spi_read_blocking(_spi, 0, data, NRF24_PAYLOAD);
    gpio_put(_csn, 1);
    return true;
  }

  void startListening() {
    writeReg(0x00, 0x03); // PWR_UP | PRIM_RX
    gpio_put(_ce, 1);
    busy_wait_us(130);
  }

  void powerUpTx() {
    writeReg(0x00, 0x02); // PWR_UP, PRIM_RX=0
    gpio_put(_ce, 0);
    busy_wait_us(130);
  }

  void powerUp() { writeReg(0x00, 0x02); }
  void powerDown() { writeReg(0x00, 0x00); }
  void setChannel(uint8_t ch) { writeReg(0x05, ch); }
  void setRfConfig(bool rate2M, uint8_t pwrCode) {
    writeReg(0x06, (rate2M ? 0x08 : 0x00) | ((pwrCode & 0x03) << 1));
  }

private:
  spi_inst_t *_spi;
  uint _csn, _ce;
  void writeReg(uint8_t reg, uint8_t val) {
    uint8_t buf[2] = {(uint8_t)(0x20 | reg), val};
    gpio_put(_csn, 0);
    spi_write_blocking(_spi, buf, 2);
    gpio_put(_csn, 1);
  }
  void writeReg(uint8_t reg, const uint8_t *data, uint8_t len) {
    uint8_t buf[1 + 5];
    buf[0] = 0x20 | reg;
    memcpy(buf + 1, data, len);
    gpio_put(_csn, 0);
    spi_write_blocking(_spi, buf, 1 + len);
    gpio_put(_csn, 1);
  }
  uint8_t readReg(uint8_t reg) {
    uint8_t buf[2] = {reg, 0};
    uint8_t out[2];
    gpio_put(_csn, 0);
    spi_write_read_blocking(_spi, buf, out, 2);
    gpio_put(_csn, 1);
    return out[1];
  }
  void flushTx() {
    uint8_t cmd = 0xE1;
    gpio_put(_csn, 0);
    spi_write_blocking(_spi, &cmd, 1);
    gpio_put(_csn, 1);
  }
};

#endif
