// nRF24L01 自检（ESP32-S3）：SPI 寄存器读回 + 发射测试，结果输出到 USB-JTAG 串口。
#include <SPI.h>
#include <string.h>
#include "driver/usb_serial_jtag.h"

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

  // 3) 像驱动一样初始化并读回关键寄存器
  writeReg(0x01, 0x3F);
  writeReg(0x02, 0x03);
  writeReg(0x03, 0x03);
  writeReg(0x04, 0x15);
  writeReg(0x05, 120);
  writeReg(0x06, 0x0E);
  jtagHex("EN_AA   ", readReg(0x01));
  jtagHex("EN_RXADDR", readReg(0x02));
  jtagHex("SETUP_AW", readReg(0x03));
  jtagHex("RETR    ", readReg(0x04));
  jtagHex("RF_CH   ", readReg(0x05));
  jtagHex("RF_SETUP", readReg(0x06));

  // 4) 发射 15 字节（信道 120），看 TX_DS / MAX_RT
  writeReg(0x00, 0x02);   // PWR_UP
  delay(2);
  writeReg(0x07, 0x70);   // 清 STATUS
  nrfSpi.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
  csLow();
  nrfSpi.transfer(0xA0);  // W_TX_PAYLOAD
  for (int i = 0; i < 15; i++) nrfSpi.transfer(0xAA);
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
