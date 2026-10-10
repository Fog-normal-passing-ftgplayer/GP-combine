// 无线链路测试（接收端）：RP2040 用 nRF24 按生产配置监听（参数见
// nrf24_common/nrf24_link_params.h），
// 收到包就打印 seq 并把板载 WS2812（GPIO16）点亮绿色；超时无包熄灭。
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include "hardware/pio.h"
#include "hardware/clocks.h"
#include "ws2812.pio.h"

// 链路参数（信道/地址/速率/CRC/载荷）来自唯一来源，与两端驱动一致
#include "../../nrf24_common/nrf24_link_params.h"

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

static void flush_cmd(uint8_t cmd) {
    cs_low();
    spi_write_blocking(spi0, &cmd, 1);
    cs_high();
}

static bool read_packet(uint8_t *data) {
    uint8_t st = read_reg(0x07);
    // RX_P_NO(bit3:1)=0b111 表示 FIFO 空（与驱动一致）
    if (!(st & 0x40) || (st & 0x0E) == 0x0E) return false;
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

    // nRF24 初始化：逐条对齐生产驱动的 begin()，参数来自共享的
    // nrf24_common/nrf24_link_params.h。
    // 原来这里是 FUSIO 地址 + 关 CRC + 信道 120 + EN_AA 0x3F，跟正式固件
    // 完全不同 —— 测通了也说明不了正式链路是好的。
    write_reg(0x00, 0x00);
    write_reg(0x01, NRF24_REG_EN_AA);
    write_reg(0x02, NRF24_REG_EN_RXADDR);
    write_reg(0x03, NRF24_REG_SETUP_AW);
    write_reg(0x04, NRF24_REG_SETUP_RETR);
    write_reg(0x05, NRF24_CHANNEL);
    write_reg(0x06, NRF24_REG_RF_SETUP);
    static const uint8_t addr[5] = NRF24_ADDR_INIT;
    write_regs(0x10, addr, 5);   // TX_ADDR
    write_regs(0x0A, addr, 5);   // RX_ADDR_P0（auto-ack 管道）
    write_reg(0x11, NRF24_PAYLOAD);
    write_reg(0x07, NRF24_REG_STATUS_CLR);
    write_reg(0x00, NRF24_REG_CONFIG_RX);   // PWR_UP | PRIM_RX | 2字节CRC
    flush_cmd(0xE1);             // 与驱动一致：上电先清干净两个 FIFO
    flush_cmd(0xE2);
    gpio_put(CE, 1);             // 开始监听
    sleep_us(150);

    // 模块自检
    uint8_t cfg = read_reg(0x00);
    printf("module check: STATUS=0x%02X CONFIG=0x%02X\r\n", read_reg(0x07), cfg);
    if ((cfg & 0x03) != 0x03) {
        printf("MODULE NOT RESPONDING (check wiring/power)\r\n");
    } else {
        printf("listening on ch%u addr=%02X%02X%02X%02X%02X...\r\n",
               (unsigned)NRF24_CHANNEL, addr[0], addr[1], addr[2], addr[3], addr[4]);
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
