// 无线链路测试（发送端）：ESP32 用 nRF24 按 FUSIO/信道120 每 100ms 发包，
// 结果通过 USB-JTAG 串口打印：TX_DS=收到ACK（接收端在听） / MAX_RT=发了没回应。
#include <SPI.h>
#include <string.h>
#include "driver/usb_serial_jtag.h"

#define CSN  14
#define CE   15
#define SCK  16
#define MISO 18
#define MOSI 17

SPIClass nrfSpi(HSPI);

static void printLine(const char *s) {
  usb_serial_jtag_write_bytes(s, strlen(s), 0);
  usb_serial_jtag_write_bytes("\r\n", 2, 0);
}

static void csLow()  { digitalWrite(CSN, LOW); }
static void csHigh() { digitalWrite(CSN, HIGH); }

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

static uint32_t txOk = 0, txFail = 0;
static uint8_t seq = 0;

// 发送 15 字节包，返回 true=收到ACK
static bool sendPacket() {
  writeReg(0x07, 0x70);               // 清 STATUS
  uint8_t pkt[15];
  memset(pkt, 0xAA, sizeof(pkt));
  pkt[0] = seq++;
  nrfSpi.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
  csLow();
  nrfSpi.transfer(0xA0);              // W_TX_PAYLOAD
  for (int i = 0; i < 15; i++) nrfSpi.transfer(pkt[i]);
  csHigh();
  nrfSpi.endTransaction();
  digitalWrite(CE, HIGH);
  delayMicroseconds(12);
  digitalWrite(CE, LOW);
  uint32_t t = micros();
  while (micros() - t < 2000) {
    uint8_t st = readReg(0x07);
    if (st & 0x20) { writeReg(0x07, 0x20); return true; }  // TX_DS
    if (st & 0x10) { writeReg(0x07, 0x10); return false; } // MAX_RT
  }
  return false;
}

void setup() {
  usb_serial_jtag_driver_config_t cfg = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
  usb_serial_jtag_driver_install(&cfg);
  delay(100);
  printLine("wireless link TX test start");

  nrfSpi.begin(SCK, MISO, MOSI, -1);
  pinMode(CSN, OUTPUT); digitalWrite(CSN, HIGH);
  pinMode(CE, OUTPUT);  digitalWrite(CE, LOW);
  delay(50);

  // 初始化与正式驱动完全一致：信道120 / FUSIO / 15字节 / 2Mbps / 自动ACK
  writeReg(0x00, 0x00);
  writeReg(0x01, 0x3F);
  writeReg(0x02, 0x03);
  writeReg(0x03, 0x03);
  writeReg(0x04, 0x15);
  writeReg(0x05, 120);
  writeReg(0x06, 0x0E);
  static const uint8_t addr[5] = {0x46, 0x55, 0x53, 0x49, 0x4F}; // "FUSIO"
  writeRegs(0x10, addr, 5);  // TX_ADDR
  writeRegs(0x0A, addr, 5);  // RX_ADDR_P0
  writeRegs(0x0B, addr, 5);  // RX_ADDR_P1
  writeReg(0x11, 15);
  writeReg(0x12, 15);
  writeReg(0x07, 0x70);

  // 模块自检：寄存器能写读回才算模块活着
  writeReg(0x00, 0x0F);
  delay(1);
  uint8_t cfgRd = readReg(0x00);
  writeReg(0x00, 0x00);
  char b[48];
  snprintf(b, sizeof(b), "module check: STATUS=0x%02X CONFIG=0x%02X",
           readReg(0x07), cfgRd);
  printLine(b);
  if (cfgRd != 0x0F) {
    printLine("MODULE NOT RESPONDING (check wiring/power)");
  } else {
    writeReg(0x00, 0x02);  // PWR_UP 保持常开
    delay(2);
    printLine("sending every 100ms...");
  }
}

void loop() {
  bool ok = sendPacket();
  if (ok) txOk++; else txFail++;
  char b[48];
  snprintf(b, sizeof(b), "seq=%u %s ok=%lu fail=%lu",
           (unsigned)seq, ok ? "TX_DS" : "MAX_RT", txOk, txFail);
  printLine(b);
  delay(100);
}
