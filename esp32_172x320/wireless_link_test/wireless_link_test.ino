// 无线链路测试（发送端）：ESP32 直接调用生产驱动的同一份实现发包，
// 结果通过 USB-JTAG 串口打印：TX_DS=收到ACK（接收端在听） / MAX_RT=发了没回应。
//
// 关键：这里 #include "../nrf24.h"（= nrf24_common 共享驱动），信道/地址/速率/
// CRC/重传次数/轮询窗口全部与正式固件一致，超时清 FIFO 的行为也一样。
// 以前这个测试自己写了一套寄存器初始化 + 自己的 sendPacket，用的是
// "FUSIO" 地址 + 关 CRC + 信道 120、2ms 超时不 flush —— 跟生产配置毫无关系，
// 所谓「链路测试通过」并不能证明正式链路是好的。
#include <SPI.h>
#include <string.h>
#include "driver/usb_serial_jtag.h"
#include "../nrf24.h"

// 与正式固件相同的引脚（见 README 的 ESP32-S3 引脚表）
#define NRF_CSN 14
#define NRF_CE  15
#define NRF_SCK 16
#define NRF_MISO 18
#define NRF_MOSI 17

SPIClass nrfSpi(HSPI);
static NRF24 radio;

static void printLine(const char *s) {
  usb_serial_jtag_write_bytes(s, strlen(s), 0);
  usb_serial_jtag_write_bytes("\r\n", 2, 0);
}

static uint32_t txOk = 0, txFail = 0;
static uint8_t seq = 0;

void setup() {
  usb_serial_jtag_driver_config_t cfg = USB_SERIAL_JTAG_DRIVER_CONFIG_DEFAULT();
  usb_serial_jtag_driver_install(&cfg);
  delay(100);
  printLine("wireless link TX test start (production config)");

  nrfSpi.begin(NRF_SCK, NRF_MISO, NRF_MOSI, -1);
  pinMode(NRF_CSN, OUTPUT); digitalWrite(NRF_CSN, HIGH);
  pinMode(NRF_CE, OUTPUT);  digitalWrite(NRF_CE, LOW);
  delay(50);
  radio.begin(nrfSpi, NRF_CSN, NRF_CE);

  static const uint8_t addr[5] = NRF24_ADDR_INIT;
  char b[128];
  snprintf(b, sizeof(b),
           "config: ch=%u addr=%02X%02X%02X%02X%02X payload=%u retr=0x%02X window=%uus",
           (unsigned)NRF24_CHANNEL, addr[0], addr[1], addr[2], addr[3], addr[4],
           (unsigned)NRF24_PAYLOAD, (unsigned)NRF24_REG_SETUP_RETR,
           (unsigned)NRF24_TX_WINDOW_US);
  printLine(b);
  printLine("sending every 100ms...");
}

void loop() {
  uint8_t pkt[NRF24_PAYLOAD];
  memset(pkt, 0xAA, sizeof(pkt));
  pkt[0] = seq++;
  bool ok = radio.writePacket(pkt);   // 与正式固件同一条发送路径
  if (ok) txOk++; else txFail++;
  char b[64];
  snprintf(b, sizeof(b), "seq=%u %s ok=%lu fail=%lu",
           (unsigned)seq, ok ? "TX_DS" : "MAX_RT", txOk, txFail);
  printLine(b);
  delay(100);
}
