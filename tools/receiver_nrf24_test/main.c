// nRF24L01 自检（RP2040 接收端）：SPI 寄存器读回 + 发射测试，结果走 USB 串口。
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"

// 参数来自唯一来源，与两端驱动一致
#include "../../nrf24_common/nrf24_link_params.h"

#define CSN   5
#define CE    6
#define SCK   2
#define MOSI  3
#define MISO  4

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

static void run_test(void) {
    printf("STATUS   0x%02X\r\n", read_reg(0x07));

    write_reg(0x00, 0x0F);
    sleep_ms(1);
    printf("CONFIG wr0F 0x%02X\r\n", read_reg(0x00));
    write_reg(0x00, 0x00);
    sleep_ms(1);
    printf("CONFIG wr00 0x%02X\r\n", read_reg(0x00));

    // 用生产配置（原值 0x3F/0x03/0x15/信道120 与正式驱动完全不同）
    write_reg(0x01, NRF24_REG_EN_AA);
    write_reg(0x02, NRF24_REG_EN_RXADDR);
    write_reg(0x03, NRF24_REG_SETUP_AW);
    write_reg(0x04, NRF24_REG_SETUP_RETR);
    write_reg(0x05, NRF24_CHANNEL);
    write_reg(0x06, NRF24_REG_RF_SETUP);
    static const uint8_t addr[5] = NRF24_ADDR_INIT;
    write_regs(0x10, addr, 5);   // TX_ADDR
    write_regs(0x0A, addr, 5);   // RX_ADDR_P0（ACK 收在这条管道上）
    write_reg(0x11, NRF24_PAYLOAD);
    printf("EN_AA    0x%02X\r\n", read_reg(0x01));
    printf("EN_RXADDR 0x%02X\r\n", read_reg(0x02));
    printf("SETUP_AW 0x%02X\r\n", read_reg(0x03));
    printf("RETR     0x%02X\r\n", read_reg(0x04));
    printf("RF_CH    0x%02X\r\n", read_reg(0x05));
    printf("RF_SETUP 0x%02X\r\n", read_reg(0x06));

    // 发射一个生产格式的包（生产信道/地址/2 字节 CRC），看 TX_DS / MAX_RT
    write_reg(0x00, NRF24_REG_CONFIG_TX);
    sleep_ms(2);
    write_reg(0x07, NRF24_REG_STATUS_CLR);
    flush_cmd(0xE1);
    flush_cmd(0xE2);
    uint8_t cmd = 0xA0;
    uint8_t payload[NRF24_PAYLOAD];
    memset(payload, 0xAA, sizeof(payload));
    cs_low();
    spi_write_blocking(spi0, &cmd, 1);
    spi_write_blocking(spi0, payload, sizeof(payload));
    cs_high();
    gpio_put(CE, 1);
    sleep_us(12);
    gpio_put(CE, 0);
    sleep_ms(10);
    uint8_t st = read_reg(0x07);
    printf("TX status 0x%02X\r\n", st);
    if (st & 0x20)      printf("TX_DS -> 发射成功并有ACK\r\n");
    else if (st & 0x10) printf("MAX_RT -> 已发射但无ACK\r\n");
    else                printf("no TX result\r\n");
    printf("---\r\n");
}

int main(void) {
    stdio_init_all();
    sleep_ms(500);
    printf("receiver nRF24 test start\r\n");

    spi_init(spi0, 8000000);
    spi_set_format(spi0, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
    gpio_set_function(SCK, GPIO_FUNC_SPI);
    gpio_set_function(MOSI, GPIO_FUNC_SPI);
    gpio_set_function(MISO, GPIO_FUNC_SPI);
    gpio_init(CSN); gpio_set_dir(CSN, GPIO_OUT); gpio_put(CSN, 1);
    gpio_init(CE);  gpio_set_dir(CE, GPIO_OUT);  gpio_put(CE, 0);
    sleep_ms(50);

    while (1) {
        run_test();
        sleep_ms(2000);
    }
}
