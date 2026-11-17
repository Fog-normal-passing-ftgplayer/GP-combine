// nRF24L01 自检（ESP32-S3）：SPI 寄存器读回 + 发射测试，结果输出到 USB-JTAG 串口。
#include <SPI.h>
#include <string.h>
#include "driver/usb_serial_jtag.h"

// 寄存器 dump / 发射测试都用生产参数，避免"测试通过但正式链路是坏的"
// （原来这里写死 0x3F/0x03/0x15/信道120，与正式驱动完全不同）。
#include "../../nrf24_common/nrf24_link_params.h"

#define NRF_CSN 14
#define NRF_CE  15
#define NRF_SCK 16
#define NRF_MISO 18
#define NRF_MOSI 17

SPIClass nrfSpi(HSPI);

static void jtagPrint(const char *s) {
  usb_serial_jtag_write_bytes(s, strlen(s), 0);
}
static void jtagPrintln(const char *s) {
  jtagPrint(s);
  jtagPrint("\r\n");
}
static void jtagHex(const char *name, uint8_t v) {
  char buf[40];
  snprintf(buf, sizeof(buf), "%s 0x%02X", name, v);
  jtagPrintln(buf);
}

static void csLow()  { digitalWrite(NRF_CSN, LOW); }
static void csHigh() { digitalWrite(NRF_CSN, HIGH); }

static uint8_t readReg(uint8_t reg) {
  uint8_t v;
  nrfSpi.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
  csLow();
  nrfSpi.transfer(reg);
  v = nrfSpi.transfer(0);
  csHigh();
  nrfSpi.endTransaction();
  return v;
}

static void writeReg(uint8_t reg, uint8_t val) {
  nrfSpi.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
  csLow();
  nrfSpi.transfer(0x20 | reg);
  nrfSpi.transfer(val);
  csHigh();
  nrfSpi.endTransaction();
}

static void writeRegs(uint8_t reg, const uint8_t *d, uint8_t n) {
  nrfSpi.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
  csLow();
  nrfSpi.transfer(0x20 | reg);
  for (uint8_t i = 0; i < n; i++) nrfSpi.transfer(d[i]);
  csHigh();
  nrfSpi.endTransaction();
}

static void runTest() {
  // 1) STATUS：真模块空闲通常是 0x0E；悬空/坏模块会读到 0x00 或 0xFF
  jtagHex("STATUS  ", readReg(0x07));

  // 2) 写读回 CONFIG：能写回去读回来 = SPI 与芯片都在工作
  writeReg(0x00, 0x0F);
  delay(1);
  jtagHex("CONFIG wr0F", readReg(0x00));
  writeReg(0x00, 0x00);
  delay(1);
  jtagHex("CONFIG wr00", readReg(0x00));

  // 3) 像驱动一样初始化并读回关键寄存器。
  //    参数来自 nrf24_common/nrf24_link_params.h（= 生产配置）：
  //    以前这里写的是 0x3F / 0x03 / 0x15 / 信道 120，跟正式驱动完全不同。
  writeReg(0x01, NRF24_REG_EN_AA);
  writeReg(0x02, NRF24_REG_EN_RXADDR);
  writeReg(0x03, NRF24_REG_SETUP_AW);
  writeReg(0x04, NRF24_REG_SETUP_RETR);
  writeReg(0x05, NRF24_CHANNEL);
  writeReg(0x06, NRF24_REG_RF_SETUP);
  static const uint8_t addr[5] = NRF24_ADDR_INIT;
  writeRegs(0x10, addr, 5);   // TX_ADDR
  writeRegs(0x0A, addr, 5);   // RX_ADDR_P0（ACK 收在这条管道上）
  writeReg(0x11, NRF24_PAYLOAD);
  jtagHex("EN_AA   ", readReg(0x01));
  jtagHex("EN_RXADDR", readReg(0x02));
  jtagHex("SETUP_AW", readReg(0x03));
  jtagHex("RETR    ", readReg(0x04));
  jtagHex("RF_CH   ", readReg(0x05));
  jtagHex("RF_SETUP", readReg(0x06));

  // 4) 发射一个生产格式的包（生产信道/地址/2 字节 CRC），看 TX_DS / MAX_RT
  writeReg(0x00, NRF24_REG_CONFIG_TX);   // PWR_UP + EN_CRC + 2字节 CRC
  delay(2);
  writeReg(0x07, NRF24_REG_STATUS_CLR);  // 清 STATUS
  nrfSpi.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
  csLow();
  nrfSpi.transfer(0xA0);  // W_TX_PAYLOAD
  for (int i = 0; i < NRF24_PAYLOAD; i++) nrfSpi.transfer(0xAA);
  csHigh();
  nrfSpi.endTransaction();
  digitalWrite(NRF_CE, HIGH);
  delayMicroseconds(12);
  digitalWrite(NRF_CE, LOW);
  delay(10);
  uint8_t st = readReg(0x07);
  jtagHex("TX status", st);
  if (st & 0x20)      jtagPrintln("TX_DS  -> 发射成功并收到ACK（无线链路 OK）");
  else if (st & 0x10) jtagPrintln("MAX_RT -> 已发射但无ACK（射频在工作，接收端没开/太远）");
  else                jtagPrintln("no TX result");
  jtagPrintln("---");
}

void setup() {
  usb_serial_jtag_driver_config_t cfg = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
  usb_serial_jtag_driver_install(&cfg);
  delay(100);
  jtagPrintln("nRF24 test start");
  nrfSpi.begin(NRF_SCK, NRF_MISO, NRF_MOSI, -1);
  pinMode(NRF_CSN, OUTPUT); digitalWrite(NRF_CSN, HIGH);
  pinMode(NRF_CE, OUTPUT);  digitalWrite(NRF_CE, LOW);
  delay(50);
  runTest();
}

void loop() {
  delay(2000);
  runTest();  // 每 2 秒重复，方便 PC 随时打开串口读到
}
