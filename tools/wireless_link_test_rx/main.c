// 无线链路测试（接收端）：RP2040 用 nRF24 监听 FUSIO/信道120，
// 收到包就打印 seq 并把板载 WS2812（GPIO16）点亮绿色；超时无包熄灭。
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "ws2812.pio.h"

#define CSN   5
#define CE    6
#define SCK   2
#define MOSI  3
#define MISO  4

#define RX_LED 16   // RP2040-Zero 板载 WS2812

static void cs_low(void)  { gpio_put(CSN, 0); }
static void cs_high(void) { gpio_put(CSN, 1); }

static uint8_t read_reg(uint8_t reg) {
    uint8_t v = 0;
    cs_low();
    spi_write_blocking(spi0, &reg, 1);
    spi_read_blocking(spi0, 0, &v, 1);
    cs_high();
    return v;
}

static void write_reg(uint8_t reg, uint8_t val) {
    uint8_t cmd = 0x20 | reg;
    cs_low();
    spi_write_blocking(spi0, &cmd, 1);
    spi_write_blocking(spi0, &val, 1);
    cs_high();
}

static void write_regs(uint8_t reg, const uint8_t *d, uint8_t n) {
    uint8_t cmd = 0x20 | reg;
    cs_low();
    spi_write_blocking(spi0, &cmd, 1);
    spi_write_blocking(spi0, d, n);
    cs_high();
}

static bool read_packet(uint8_t *data) {
    uint8_t st = read_reg(0x07);
    if (!(st & 0x40)) return false;   // 无 RX_DR
    write_reg(0x07, 0x40);
    uint8_t cmd = 0x61;               // R_RX_PAYLOAD
    cs_low();
    spi_write_blocking(spi0, &cmd, 1);
    spi_read_blocking(spi0, 0, data, 15);
    cs_high();
    return true;
}

static void ws2812_init(PIO pio, uint sm, uint pin) {
    uint offset = pio_add_program(pio, &ws2812_program);
    pio_gpio_init(pio, pin);
    pio_sm_set_consecutive_pindirs(pio, sm, pin, 1, true);
    pio_sm_config c = ws2812_program_get_default_config(offset);
    sm_config_set_sideset_pins(&c, pin);
    sm_config_set_out_shift(&c, false, true, 24);
    sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_TX);
    pio_sm_init(pio, sm, offset, &c);
    pio_sm_set_enabled(pio, sm, true);
}

static void ws2812_put(PIO pio, uint sm, uint8_t r, uint8_t g, uint8_t b) {
    uint32_t grb = ((uint32_t)g << 16) | ((uint32_t)r << 8) | b;
    pio_sm_put_blocking(pio, sm, grb << 8u);
}

int main(void) {
    stdio_init_all();
    sleep_ms(500);
    printf("wireless link RX test start\r\n");

    spi_init(spi0, 8000000);
    spi_set_format(spi0, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
    gpio_set_function(SCK, GPIO_FUNC_SPI);
    gpio_set_function(MOSI, GPIO_FUNC_SPI);
    gpio_set_function(MISO, GPIO_FUNC_SPI);
    gpio_init(CSN); gpio_set_dir(CSN, GPIO_OUT); gpio_put(CSN, 1);
    gpio_init(CE);  gpio_set_dir(CE, GPIO_OUT);  gpio_put(CE, 0);
    sleep_ms(50);

    // nRF24 初始化，与发送端一致：信道120 / FUSIO / 15字节 / 2Mbps / 自动ACK
    write_reg(0x00, 0x00);
    write_reg(0x01, 0x3F);
    write_reg(0x02, 0x03);
    write_reg(0x03, 0x03);
    write_reg(0x04, 0x15);
    write_reg(0x05, 120);
    write_reg(0x06, 0x0E);
    static const uint8_t addr[5] = {0x46, 0x55, 0x53, 0x49, 0x4F}; // "FUSIO"
    write_regs(0x10, addr, 5);   // TX_ADDR
    write_regs(0x0A, addr, 5);   // RX_ADDR_P0
    write_regs(0x0B, addr, 5);   // RX_ADDR_P1
    write_reg(0x11, 15);
    write_reg(0x12, 15);
    write_reg(0x07, 0x70);
    write_reg(0x00, 0x03);       // PWR_UP | PRIM_RX
    gpio_put(CE, 1);             // 开始监听
    sleep_us(150);

    // 模块自检
    uint8_t cfg = read_reg(0x00);
    printf("module check: STATUS=0x%02X CONFIG=0x%02X\r\n", read_reg(0x07), cfg);
    if ((cfg & 0x03) != 0x03) {
        printf("MODULE NOT RESPONDING (check wiring/power)\r\n");
    } else {
        printf("listening on ch120 FUSIO...\r\n");
    }

    PIO pio = pio1;
    uint sm = 0;
    ws2812_init(pio, sm, RX_LED);
    ws2812_put(pio, sm, 0, 0, 0);

    uint32_t count = 0;
    uint32_t lastRx = 0;
    while (1) {
        uint8_t pkt[15];
        if (read_packet(pkt)) {
            count++;
            lastRx = to_ms_since_boot(get_absolute_time());
            printf("RX seq=%u total=%lu\r\n", pkt[0], count);
            ws2812_put(pio, sm, 0, 80, 0);   // 收到包：绿色
        }
        if (lastRx && to_ms_since_boot(get_absolute_time()) - lastRx > 300) {
            ws2812_put(pio, sm, 0, 0, 0);    // 300ms 无包：熄灭
            lastRx = 0;
        }
        tight_loop_contents();
    }
}
