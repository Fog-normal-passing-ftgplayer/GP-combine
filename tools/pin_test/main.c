// 最小引脚自检固件：只测 GPIO2/3/4/5，不碰配置区。
// 用法：BOOTSEL 刷入后打开 USB 串口（115200），
//   u = 输入+上拉（默认）   d = 输入+下拉   o = 输出 1Hz 翻转（会驱动引脚，勿短接）
// 正常情况下：上拉时悬空读 1，短接到 GND 读 0；下拉时悬空读 0，短到 3V3 读 1。
#include <stdio.h>
#include "pico/stdlib.h"
#include "hardware/gpio.h"

static const uint PINS[] = {2, 3, 4, 5};
#define NPINS (sizeof(PINS) / sizeof(PINS[0]))

static void as_input(bool pullup) {
    for (unsigned i = 0; i < NPINS; i++) {
        gpio_init(PINS[i]);
        gpio_set_dir(PINS[i], GPIO_IN);
        if (pullup) gpio_pull_up(PINS[i]);
        else gpio_pull_down(PINS[i]);
    }
}

static void as_output(void) {
    for (unsigned i = 0; i < NPINS; i++) {
        gpio_init(PINS[i]);
        gpio_set_dir(PINS[i], GPIO_OUT);
        gpio_put(PINS[i], 0);
    }
}

int main() {
    stdio_init_all();
    as_input(true);
    printf("\npin_test ready (GP2/3/4/5)\n");
    printf("u=pull-up  d=pull-down  o=output 1Hz (do not short outputs)\n");

    bool out_mode = false;
    bool level = false;
    absolute_time_t next = make_timeout_time_ms(200);

    while (true) {
        int c = getchar_timeout_us(0);
        if (c == 'u') {
            out_mode = false; as_input(true);
            printf("mode: input pull-up\n");
        } else if (c == 'd') {
            out_mode = false; as_input(false);
            printf("mode: input pull-down\n");
        } else if (c == 'o') {
            out_mode = !out_mode;
            if (out_mode) { as_output(); printf("mode: output 1Hz -- meters only, do NOT short\n"); }
            else { as_input(true); printf("mode: input pull-up\n"); }
        }

        if (time_reached(next)) {
            next = make_timeout_time_ms(200);
            if (!out_mode) {
                printf("GP2=%d GP3=%d GP4=%d GP5=%d\n",
                       gpio_get(2), gpio_get(3), gpio_get(4), gpio_get(5));
            } else {
                level = !level;
                for (unsigned i = 0; i < NPINS; i++) gpio_put(PINS[i], level);
                printf("OUT=%d\n", level ? 1 : 0);
            }
        }
        sleep_ms(10);
    }
}
