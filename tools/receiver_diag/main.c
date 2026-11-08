// GP-Combine 接收端现场诊断固件（RP2040-Zero）
//
// 目的：绕开 GP2040-CE（存储/驱动/usb 那一整套），只回答三件事：
//   1. 配置扇区里存的到底是什么（paired / inputMode 有没有被清掉）
//   2. nRF24 模块在 SPI 上到底活没活（寄存器写-读回）
//   3. 发送端有没有在**生产链路参数**（信道/地址/速率/CRC）上发包，包里的 mode 字节是什么
//
// 全部结果走 USB 串口打印。板载 WS2812(GPIO16)：开机三下白闪，
// 之后 绿=正在收包 / 蓝=收不到包。

#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "pico/multicore.h"
#include "ws2812.pio.h"

// 信道/地址/速率/CRC/载荷/重传全部来自生产固件同一份定义。
// 这里曾经硬编码 100(2500MHz)/0x13，与正式固件(84/0x03)不同，
// 导致这个「现场诊断」永远收不到包、只会误导排障。
#include "../../nrf24_common/nrf24_link_params.h"

#define PIN_CSN  5
#define PIN_CE   6
#define PIN_SCK  2
#define PIN_MOSI 3
#define PIN_MISO 4
#define PIN_LED  16

#define CFG_XIP    0x101F8000u  // FlashPROM / GP2040-CE 配置区
#define CFG_LEN    0x8000u
#define ESPCFG_XIP 0x101F7000u  // uart_link 的 ESP 配置镜像

static PIO led_pio = pio0;
static uint led_sm = 0;

static void led_rgb(uint8_t r, uint8_t g, uint8_t b) {
    pio_sm_put_blocking(led_pio, led_sm,
        (uint32_t)(((uint32_t)g << 16) | ((uint32_t)r << 8) | b) << 8u);
}

static void cs_low(void)  { gpio_put(PIN_CSN, 0); }
static void cs_high(void) { gpio_put(PIN_CSN, 1); }

static uint8_t nrf_read(uint8_t reg) {
    uint8_t buf[2] = { reg, 0 }, out[2] = { 0, 0 };
    cs_low();
    spi_write_read_blocking(spi0, buf, out, 2);
    cs_high();
    return out[1];
}

static void nrf_write(uint8_t reg, uint8_t val) {
    uint8_t buf[2] = { (uint8_t)(0x20 | reg), val };
    cs_low();
    spi_write_blocking(spi0, buf, 2);
    cs_high();
}

static void nrf_write_buf(uint8_t reg, const uint8_t *data, uint8_t len) {
    uint8_t buf[6];
    buf[0] = (uint8_t)(0x20 | reg);
    memcpy(buf + 1, data, len);
    cs_low();
    spi_write_blocking(spi0, buf, len + 1);
    cs_high();
}

static void nrf_read_addr(uint8_t reg, uint8_t *out, uint8_t len) {
    cs_low();
    spi_write_blocking(spi0, &reg, 1);
    spi_read_blocking(spi0, 0, out, len);
    cs_high();
}

static int nrf_read_payload(uint8_t *data) {
    uint8_t st = nrf_read(0x07);
    // 与正式驱动一致：RX_P_NO(bit3:1)=0b111 表示 RX FIFO 空
    if (!(st & 0x40) || (st & 0x0E) == 0x0E) return 0;
    nrf_write(0x07, 0x40);
    uint8_t cmd = 0x61;
    cs_low();
    spi_write_blocking(spi0, &cmd, 1);
    spi_read_blocking(spi0, 0, data, NRF24_PAYLOAD);
    cs_high();
    return 1;
}

static uint32_t crc32_update(uint32_t crc, uint8_t b) {
    crc ^= b;
    for (int i = 0; i < 8; i++)
        crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(crc & 1)));
    return crc;
}

static void dump_config(void) {
    const uint8_t *p = (const uint8_t *)CFG_XIP;
    uint32_t ff = 0;
    uint32_t crc = 0xFFFFFFFFu;
    for (uint32_t i = 0; i < CFG_LEN; i++) {
        if (p[i] == 0xFF) ff++;
        crc = crc32_update(crc, p[i]);
    }
    printf("CFG addr=0x%08X len=%u ff=%u crc=%08X\n",
           (unsigned)CFG_XIP, (unsigned)CFG_LEN, (unsigned)ff,
           (unsigned)(crc ^ 0xFFFFFFFFu));
    for (uint32_t i = 0; i < 640; i += 20) {
        printf("CFG %04X ", (unsigned)i);
        for (uint32_t j = 0; j < 20; j++) printf("%02X", p[i + j]);
        printf("\n");
    }
    const uint8_t *e = (const uint8_t *)ESPCFG_XIP;
    printf("ESPCFG ");
    for (int i = 0; i < 32; i++) printf("%02X", e[i]);
    printf("  magic=%c%c%c%c\n", e[0], e[1], e[2], e[3]);
}

static void hello_led(void) {
    for (int i = 0; i < 3; i++) {
        led_rgb(90, 90, 90);
        sleep_ms(150);
        led_rgb(0, 0, 0);
        sleep_ms(150);
    }
}

int main(void) {
    stdio_init_all();

    uint offset = pio_add_program(led_pio, &ws2812_program);
    ws2812_program_init(led_pio, led_sm, offset, PIN_LED, 800000, false);
    led_rgb(0, 0, 0);

    // 给主机 2.5s 枚举并打开 CDC（这样读到的是从第一行开始的完整输出）
    sleep_ms(2500);
    printf("\n\n[diag boot] t=%u ms\n", (unsigned)to_ms_since_boot(get_absolute_time()));
    printf("\n=== GP-Combine RX DIAG ===\n");
    hello_led();
    printf("alive, led done\n");

    dump_config();

    // ---- 复现"开机保存配置"的锁死路径 ----
    // GP2040::setup() 一开始就 Storage::init()，配置无效时会 save()→EEPROM.commit()
    // →50ms 后 alarm 里 writeToFlash()→multicore_lockout_start_blocking()。
    // 而 core1 要到 main() 后半段才 launch。这里 core1 从来没启动，等价复现。
    printf("--- multicore lockout test ---\n");
    printf("victim core1 initialized = %d\n",
           (int)multicore_lockout_victim_is_initialized(1));
    led_rgb(80, 80, 0);   // 黄：进入测试
    printf("calling multicore_lockout_start_blocking()...\n");
    multicore_lockout_start_blocking();
    printf("lockout returned OK (NO hang)\n");
    multicore_lockout_end_blocking();
    led_rgb(0, 80, 0);    // 绿：没卡

    // ---- nRF24 接收配置：与正式固件逐字节一致 ----
    spi_init(spi0, 4000000);
    spi_set_format(spi0, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
    gpio_set_function(PIN_SCK, GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_init(PIN_CSN); gpio_set_dir(PIN_CSN, GPIO_OUT); gpio_put(PIN_CSN, 1);
    gpio_init(PIN_CE);  gpio_set_dir(PIN_CE, GPIO_OUT);  gpio_put(PIN_CE, 0);
    sleep_ms(20);

    printf("--- nRF24 registers BEFORE init ---\n");
    printf("CONFIG=%02X EN_AA=%02X EN_RXADDR=%02X SETUP_AW=%02X SETUP_RETR=%02X\n",
           nrf_read(0x00), nrf_read(0x01), nrf_read(0x02), nrf_read(0x03), nrf_read(0x04));
    printf("RF_CH=%02X RF_SETUP=%02X STATUS=%02X FIFO=%02X\n",
           nrf_read(0x05), nrf_read(0x06), nrf_read(0x07), nrf_read(0x17));

    nrf_write(0x00, 0x00);
    nrf_write(0x01, NRF24_REG_EN_AA);
    nrf_write(0x02, NRF24_REG_EN_RXADDR);
    nrf_write(0x03, NRF24_REG_SETUP_AW);
    nrf_write(0x04, NRF24_REG_SETUP_RETR);
    nrf_write(0x05, NRF24_CHANNEL);
    nrf_write(0x06, NRF24_REG_RF_SETUP);
    static const uint8_t addr[5] = NRF24_ADDR_INIT;
    nrf_write_buf(0x10, addr, 5);
    nrf_write_buf(0x0A, addr, 5);
    nrf_write(0x11, NRF24_PAYLOAD);
    nrf_write(0x07, NRF24_REG_STATUS_CLR);
    nrf_write(0x00, NRF24_REG_CONFIG_RX);
    gpio_put(PIN_CE, 1);
    sleep_us(150);

    uint8_t rd_addr[5] = { 0 };
    nrf_read_addr(0x0A, rd_addr, 5);
    printf("--- nRF24 registers AFTER init ---\n");
    printf("CONFIG=%02X EN_AA=%02X EN_RXADDR=%02X RF_CH=%02X RF_SETUP=%02X\n",
           nrf_read(0x00), nrf_read(0x01), nrf_read(0x02), nrf_read(0x05), nrf_read(0x06));
    printf("RX_ADDR_P0=%02X%02X%02X%02X%02X RX_PW_P0=%02X\n",
           rd_addr[0], rd_addr[1], rd_addr[2], rd_addr[3], rd_addr[4], nrf_read(0x11));
    printf("expected CONFIG=%02X RF_CH=%02X RF_SETUP=%02X addr=%02X%02X%02X%02X%02X width=%02X\n",
           NRF24_REG_CONFIG_RX, NRF24_CHANNEL, NRF24_REG_RF_SETUP,
           addr[0], addr[1], addr[2], addr[3], addr[4], NRF24_PAYLOAD);
    printf("--- listening (channel %u = %u MHz, 2Mbps, %uB payload) ---\n",
           NRF24_CHANNEL, 2400u + NRF24_CHANNEL, NRF24_PAYLOAD);

    uint32_t n = 0, hb = 0, last_rx_ms = 0;
    uint8_t modes[8];
    uint32_t mode_cnt[8];
    memset(modes, 0, sizeof(modes));
    memset(mode_cnt, 0, sizeof(mode_cnt));

    absolute_time_t t_next = make_timeout_time_ms(1000);
    while (1) {
        uint8_t pkt[NRF24_PAYLOAD];
        if (nrf_read_payload(pkt)) {
            n++;
            last_rx_ms = to_ms_since_boot(get_absolute_time());
            printf("PKT %5u mode=%02X data=", (unsigned)n, pkt[0]);
            for (int i = 0; i < NRF24_PAYLOAD; i++) printf("%02X", pkt[i]);
            printf("\n");
            int slot = -1;
            for (int i = 0; i < 8; i++) {
                if (mode_cnt[i] == 0 || modes[i] == pkt[0]) { slot = i; modes[i] = pkt[0]; break; }
            }
            if (slot >= 0) mode_cnt[slot]++;
            led_rgb(0, 60, 0);
        }
        if (time_reached(t_next)) {
            t_next = make_timeout_time_ms(1000);
            uint32_t now = to_ms_since_boot(get_absolute_time());
            uint8_t rpd = nrf_read(0x09) & 0x01;
            uint8_t fifo = nrf_read(0x17);
            uint8_t obs = nrf_read(0x08);
            printf("HB t=%us pkts=%u last_rx=%us rpd=%u fifo=%02X lost=%u\n",
                   (unsigned)(now / 1000), (unsigned)n,
                   (unsigned)(last_rx_ms ? (now - last_rx_ms) / 1000 : 999),
                   rpd, fifo, (unsigned)(obs >> 4));
            for (int i = 0; i < 8; i++)
                if (mode_cnt[i]) printf("   seen mode=%02X x%u\n", modes[i], (unsigned)mode_cnt[i]);
            if (n > 0) led_rgb(0, 60, 0); else led_rgb(0, 0, 60);
            hb++;
            if (hb >= 600) break;
        }
        tight_loop_contents();
    }
    printf("diag done\n");
    return 0;
}
