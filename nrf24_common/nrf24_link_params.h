#ifndef NRF24_LINK_PARAMS_H_
#define NRF24_LINK_PARAMS_H_
/* ---------------------------------------------------------------------------
 * nRF24 无线链路「两端必须一致」的参数 —— 唯一来源
 *
 * 发送端 ESP32 驱动（nrf24_common/nrf24_esp32.h）、接收端 RP2040 驱动
 * （headers/addons/nrf24.h）、以及 tools/ 与两个 sketch 目录里的诊断程序，
 * 全都包含这一个文件。改链路就改这里，别在任何一侧再抄一份。
 *
 * 为什么会有这个文件：以前每一侧都自己写了一套常量，结果诊断工具用的是
 * "FUSIO" 地址 + 关 CRC + 信道 120，而生产配置是 0xE7 地址 + 2 字节 CRC +
 * 信道 100 —— 所谓「链路测试通过」从来没验证过真正的链路，发送端 TX FIFO
 * 淤积那个「时连时断」的 bug 就是这么活下来的。
 *
 * 纯宏、不依赖 Arduino 或 pico-sdk，C 与 C++ 都能包含。
 * ------------------------------------------------------------------------- */

/* 静态载荷宽度：两端 RX_PW_P0 必须都是它 */
#define NRF24_PAYLOAD 15

/* 射频信道 = 2400 + NRF24_CHANNEL (MHz)，可用 0..125 => 2400~2525 MHz。
 * 原来用 100 = 2500 MHz，正好压在 nRF24L01+ 频段的最上沿：廉价模块的匹配网络/
 * 带通是按 2.4~2.4835 GHz 调的，越往上发射功率和灵敏度掉得越多（实测
 * “110 = 2510 MHz 丢包明显更多”就是这个原因，说明一直工作在模块最差的一段）。
 * 84 = 2484 MHz：在 WiFi 1~11 信道（2401~2473 MHz）之上，又比 2500 低 16 MHz。
 * 注意：若本机 AP 开在 WiFi 13 信道（2461~2483 MHz），两端一起改到别的空闲
 * 信道（例如 4 = 2404 MHz）。**两端必须一致。** */
#ifndef NRF24_CHANNEL
#define NRF24_CHANNEL 84
#endif

/* 5 字节地址：TX_ADDR 与 RX_ADDR_P0（auto-ack 管道）都用它 */
#define NRF24_ADDR_INIT { 0xE7, 0xE7, 0xE7, 0xE7, 0xE7 }

/* 寄存器值 —— 两端必须一致 */
#define NRF24_REG_SETUP_AW   0x03   /* SETUP_AW: 5 字节地址 */
#define NRF24_REG_EN_AA      0x01   /* EN_AA: 仅 pipe0 开 auto-ack */
#define NRF24_REG_EN_RXADDR  0x01   /* EN_RXADDR: 仅 pipe0 */
#define NRF24_REG_RF_SETUP   0x0E   /* RF_SETUP: 2 Mbps, 0 dBm */
#define NRF24_REG_CONFIG_TX  0x0E   /* CONFIG: PWR_UP | EN_CRC | CRCO(2 字节 CRC) */
#define NRF24_REG_CONFIG_RX  0x0F   /* 上面 + PRIM_RX */
#define NRF24_REG_STATUS_CLR 0x70   /* 写 1 清 RX_DR / TX_DS / MAX_RT */

/* SETUP_RETR：ARD = 250 µs (0000)，ARC = 3 -> 一共 4 次尝试。
 * （250 µs 是 1/2 Mbps 下允许的最小重传间隔；ARC 从 3 降到 1 会让丢包率按
 *   平方放大，是「时连时断」变频繁的另一个原因） */
#define NRF24_REG_SETUP_RETR 0x03
#define NRF24_ATTEMPTS       4
#define NRF24_ARD_US         250

/* 一次发送在空中的时间：前导 1B + 地址 5B + 包控制 9bit + 载荷 15B + CRC 2B
 *   = (8 + 40 + 9 + 120 + 16) bit = 193 bit @ 2 Mbps ≈ 96.5 µs */
#define NRF24_AIR_TIME_US 97

/* 最坏情况（每次都没 ACK）MAX_RT 置位的时刻 */
#define NRF24_MAXRT_US \
    (NRF24_ATTEMPTS * NRF24_AIR_TIME_US + (NRF24_ATTEMPTS - 1) * NRF24_ARD_US)

/* 发送端轮询窗口必须明显大于最坏重传时序，否则会在 MAX_RT 置位之前就退出循环、
 * 把包留在 TX FIFO 里（旧 esp32/nrf24.h 正是这样坏的：2000 µs 窗口 vs
 * ≈1886 µs 的最坏时序，只差 100 µs，边界上随机命中 -> 旧包排队 -> 时连时断）。
 * 这里留 900 µs 余量；nrf24_esp32.h 里用 static_assert 钉死。 */
#define NRF24_TX_WINDOW_US (NRF24_MAXRT_US + 900)

#endif /* NRF24_LINK_PARAMS_H_ */
