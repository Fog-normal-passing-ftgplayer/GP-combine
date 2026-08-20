// nRF24L01 自检（RP2040 接收端）：SPI 寄存器读回 + 发射测试，结果走 USB 串口。
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"

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

static void run_test(void) {
    printf("STATUS   0x%02X\r\n", read_reg(0x07));

    write_reg(0x00, 0x0F);
    sleep_ms(1);
    printf("CONFIG wr0F 0x%02X\r\n", read_reg(0x00));
    write_reg(0x00, 0x00);
    sleep_ms(1);
    printf("CONFIG wr00 0x%02X\r\n", read_reg(0x00));

    write_reg(0x01, 0x3F);
    write_reg(0x02, 0x03);
    write_reg(0x03, 0x03);
    write_reg(0x04, 0x15);
    write_reg(0x05, 120);
    write_reg(0x06, 0x0E);
    printf("EN_AA    0x%02X\r\n", read_reg(0x01));
    printf("EN_RXADDR 0x%02X\r\n", read_reg(0x02));
    printf("SETUP_AW 0x%02X\r\n", read_reg(0x03));
    printf("RETR     0x%02X\r\n", read_reg(0x04));
    printf("RF_CH    0x%02X\r\n", read_reg(0x05));
    printf("RF_SETUP 0x%02X\r\n", read_reg(0x06));

    // 发射 15 字节（信道 120），看 TX_DS / MAX_RT
    write_reg(0x00, 0x02);
    sleep_ms(2);
    write_reg(0x07, 0x70);
    uint8_t cmd = 0xA0;
    uint8_t payload[15];
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
