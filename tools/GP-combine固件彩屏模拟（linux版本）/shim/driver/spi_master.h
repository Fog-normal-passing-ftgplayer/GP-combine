// 宿主机仿真用的 ESP-IDF SPI master 垫片。
// 170x320 那份固件的推屏走 IDF 的 spi_bus_*/spi_device_*（带 DMA 队列），
// 不是 Arduino 的 SPI.transfer。仿真里全部吞掉。
#pragma once
#include <cstdint>
#include <cstddef>

typedef int esp_err_t;
#define ESP_OK   0
#define ESP_FAIL (-1)

typedef struct spi_device_t *spi_device_handle_t;
typedef int spi_host_device_t;
#define SPI2_HOST 1
#define SPI3_HOST 2

#define SPI_DMA_CH_AUTO 3

#define SPI_TRANS_USE_TXDATA (1 << 15)
#define SPI_TRANS_USE_RXDATA (1 << 14)
#define SPI_TRANS_MODE_QIO   (1 << 5)

typedef struct {
    int mosi_io_num, miso_io_num, sclk_io_num, quadwp_io_num, quadhd_io_num;
    int data0_io_num, data1_io_num, data2_io_num, data3_io_num;
    int max_transfer_sz;
    int flags;
    int intr_flags;
} spi_bus_config_t;

typedef struct {
    int command_bits, address_bits, dummy_bits;
    int mode, duty_cycle_pos, cs_ena_pretrans, cs_ena_posttrans;
    int clock_speed_hz;
    int input_delay_ns;
    int spics_io_num;
    int flags;
    int queue_size;
    void (*pre_cb)(void *);
    void (*post_cb)(void *);
} spi_device_interface_config_t;

typedef struct {
    uint32_t flags;
    uint16_t cmd;
    uint64_t addr;
    size_t length;
    uint32_t rxlength;
    void *user;
    union { const void *tx_buffer; uint8_t tx_data[4]; };
    union { void *rx_buffer; uint8_t rx_data[4]; };
} spi_transaction_t;

static inline esp_err_t spi_bus_initialize(spi_host_device_t, const spi_bus_config_t *, int) { return ESP_OK; }
static inline esp_err_t spi_bus_free(spi_host_device_t) { return ESP_OK; }
static inline esp_err_t spi_bus_add_device(spi_host_device_t, const spi_device_interface_config_t *,
                                           spi_device_handle_t *out) {
    static int anchor;
    if (out) *out = (spi_device_handle_t)&anchor;
    return ESP_OK;
}
static inline esp_err_t spi_bus_remove_device(spi_device_handle_t) { return ESP_OK; }
static inline esp_err_t spi_device_queue_trans(spi_device_handle_t, spi_transaction_t *, uint32_t) { return ESP_OK; }
static inline esp_err_t spi_device_get_trans_result(spi_device_handle_t, spi_transaction_t **t, uint32_t) {
    if (t) *t = nullptr;
    return ESP_OK;
}
static inline esp_err_t spi_device_polling_transmit(spi_device_handle_t, spi_transaction_t *) { return ESP_OK; }
static inline esp_err_t spi_device_acquire_bus(spi_device_handle_t, uint32_t) { return ESP_OK; }
static inline void spi_device_release_bus(spi_device_handle_t) {}
