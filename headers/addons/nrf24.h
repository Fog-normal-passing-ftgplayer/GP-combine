#ifndef _NRF24_PICO_H_
#define _NRF24_PICO_H_

// Minimal nRF24L01+ driver for RP2040 (pico-sdk): fixed channel/address,
// 2Mbps, auto-ACK, static 15-byte payload.

#include "hardware/spi.h"
#include "hardware/gpio.h"
#include "pico/time.h"
#include <stdint.h>
#include <string.h>

// 信道/地址/速率/CRC/载荷 全部来自共享文件，发送端（nrf24_common/nrf24_esp32.h）
// 和诊断工具包含的是同一份 —— 以前两侧各写一份，诊断工具的参数跟生产完全不同
// （FUSIO 地址 + 关 CRC + 信道 120），所谓「链路测试通过」从来没验证过真正的链路。
#include "../../nrf24_common/nrf24_link_params.h"

class NRF24 {
public:
  void begin(spi_inst_t *spi, uint csn, uint ce) {
    _spi = spi; _csn = csn; _ce = ce;
    gpio_init(_csn); gpio_set_dir(_csn, GPIO_OUT); gpio_put(_csn, 1);
    gpio_init(_ce); gpio_set_dir(_ce, GPIO_OUT); gpio_put(_ce, 0);
    spi_init(_spi, 4000000);
    spi_set_format(_spi, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
    sleep_ms(10);
    writeReg(0x00, 0x00);                   // power down
    writeReg(0x01, NRF24_REG_EN_AA);        // EN_AA: 仅 pipe0（auto-ack）
    writeReg(0x02, NRF24_REG_EN_RXADDR);    // EN_RXADDR: 仅 pipe0
    writeReg(0x03, NRF24_REG_SETUP_AW);     // SETUP_AW: 5-byte addresses
    writeReg(0x04, NRF24_REG_SETUP_RETR);   // SETUP_RETR: ARD=250us(0000), ARC=3
    writeReg(0x05, NRF24_CHANNEL);          // RF_CH
    writeReg(0x06, NRF24_REG_RF_SETUP);     // RF_SETUP: 2Mbps, 0dBm
    static const uint8_t addr[5] = NRF24_ADDR_INIT;
    writeReg(0x10, addr, 5);                // TX_ADDR
    writeReg(0x0A, addr, 5);                // RX_ADDR_P0 (auto-ack pipe)
    writeReg(0x11, NRF24_PAYLOAD);          // RX_PW_P0
    writeReg(0x07, NRF24_REG_STATUS_CLR);   // clear STATUS
    writeReg(0x00, NRF24_REG_CONFIG_RX);    // PWR_UP | PRIM_RX | 2字节CRC
    flushTx();                       // 上电/重 init 后 FIFO 里可能还留着残包
    flushRx();
    gpio_put(_ce, 1);
    sleep_us(150);
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
    // RX_P_NO (bit3:1) = 0b111 表示 RX FIFO 空；只认 RX_DR 有可能读到空包
    if (!(st & 0x40) || (st & 0x0E) == 0x0E) return false;
    writeReg(0x07, 0x40);
    gpio_put(_csn, 0);
    uint8_t cmd = 0x61; // R_RX_PAYLOAD
    spi_write_blocking(_spi, &cmd, 1);
    spi_read_blocking(_spi, 0, data, NRF24_PAYLOAD);
    gpio_put(_csn, 1);
    return true;
  }

  void startListening() {
    writeReg(0x00, NRF24_REG_CONFIG_RX); // PWR_UP | PRIM_RX | 2字节CRC
    gpio_put(_ce, 1);
    busy_wait_us(130);
  }

  void powerUpTx() {
    writeReg(0x00, NRF24_REG_CONFIG_TX); // PWR_UP, PRIM_RX=0, 2字节CRC
    gpio_put(_ce, 0);
    busy_wait_us(130);
  }

  void powerUp() { writeReg(0x00, NRF24_REG_CONFIG_TX); }
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
  void flushCmd(uint8_t cmd) {
    gpio_put(_csn, 0);
    spi_write_blocking(_spi, &cmd, 1);
    gpio_put(_csn, 1);
  }
  void flushTx() { flushCmd(0xE1); }   // FLUSH_TX
  void flushRx() { flushCmd(0xE2); }   // FLUSH_RX
};

#endif
