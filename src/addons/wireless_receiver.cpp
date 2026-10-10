#include "addons/wireless_receiver.h"
#include "addons/nrf24.h"
#include "NeoPico.h"
#include "storagemanager.h"
#include "gamepad.h"
#include "system.h"
#include "tusb.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"

NRF24 radio;

#if WIRELESS_RX_RGB_LED_PIN >= 0
static NeoPico rxNeo;
static uint32_t rxNeoFrame[100] = {0};

static void rxNeoSetColor(uint8_t r, uint8_t g, uint8_t b) {
    rxNeoFrame[0] = ((uint32_t)g << 16) | ((uint32_t)r << 8) | b;
    rxNeo.SetFrame(rxNeoFrame);
    rxNeo.Show();
}
#endif

bool WirelessReceiverAddon::available() {
    return WIRELESS_RECEIVER_ENABLED;
}

void WirelessReceiverAddon::setup() {
    // SPI0 pins for the radio
    gpio_set_function(WIRELESS_RX_SCK_PIN, GPIO_FUNC_SPI);
    gpio_set_function(WIRELESS_RX_MOSI_PIN, GPIO_FUNC_SPI);
    gpio_set_function(WIRELESS_RX_MISO_PIN, GPIO_FUNC_SPI);
    radio.begin(spi0, WIRELESS_RX_CSN_PIN, WIRELESS_RX_CE_PIN);

    paired = Storage::getInstance().getGamepadOptions().wirelessPaired;
    rxButtons = 0;
    rxDpad = 0;
    rxlx = GAMEPAD_JOYSTICK_MID; rxly = GAMEPAD_JOYSTICK_MID;
    rxrx = GAMEPAD_JOYSTICK_MID; rxry = GAMEPAD_JOYSTICK_MID;
    rxlt = 0; rxrt = 0;
    lastPacketTime = 0;
    lastRadioReinit = 0;
    pendingMode = 0;
    pendingModeCount = 0;
    // 注意：这里**不能**调 tud_disconnect()。addon setup 跑在 tud_init() 之前，
    // 而 RP2040 的 dcd_disconnect() 会读写还处于复位状态的 usb_hw（硬件置位/清零别名
    // 是读-改-写），总线会直接锁死 → 整机黑屏、USB 完全不出现。改到 preprocess() 里做。
    usbHidden = false;
    radio.startListening();

#if WIRELESS_RX_RGB_LED_PIN >= 0
    // RP2040-Zero 板载 WS2812 状态灯（pio1 空闲）
    rxNeo.Setup(WIRELESS_RX_RGB_LED_PIN, 1, LED_FORMAT_GRB, pio1, 0);
    rxNeo.Off();
    // 开机三闪：证明"固件是 Zero 版 + 状态灯可用"，闪完才进入状态显示
    for (int i = 0; i < 3; i++) {
        rxNeoSetColor(80, 80, 80);
        sleep_ms(80);
        rxNeo.Off();
        sleep_ms(120);
    }
#else
    gpio_init(WIRELESS_RX_LED_PIN);
    gpio_set_dir(WIRELESS_RX_LED_PIN, GPIO_OUT);
    gpio_put(WIRELESS_RX_LED_PIN, 0);
    for (int i = 0; i < 3; i++) {
        gpio_put(WIRELESS_RX_LED_PIN, 1);
        sleep_ms(80);
        gpio_put(WIRELESS_RX_LED_PIN, 0);
        sleep_ms(120);
    }
#endif
    lastLedToggle = 0;
    ledOn = false;
}

void WirelessReceiverAddon::handlePacket(const uint8_t *pkt) {
    uint8_t mode = pkt[0];
    GamepadOptions &opts = Storage::getInstance().getGamepadOptions();

    // 模式合法性校验：非法值（空中干扰/异常包）绝不能存进配置，否则重启后卡死
    if (mode != 0xFF && mode > 16) {
        return;
    }

    // 0xFF = 发送端还没拿到 Pico 的真实输入模式：不配对、不切模式，只缓存输入
    if (mode == 0xFF) {
        rxButtons = pkt[2] | ((uint16_t)pkt[3] << 8);
        rxDpad = pkt[4];
        rxlx = pkt[5] | ((uint16_t)pkt[6] << 8);
        rxly = pkt[7] | ((uint16_t)pkt[8] << 8);
        rxrx = pkt[9] | ((uint16_t)pkt[10] << 8);
        rxry = pkt[11] | ((uint16_t)pkt[12] << 8);
        rxlt = pkt[13];
        rxrt = pkt[14];
        lastPacketTime = to_ms_since_boot(get_absolute_time());
        return;
    }

    // 配对 / 切模式都要写 flash + 重启。链路抖一下就可能收到一个模式字节不对的包，
    // 收到就立刻重启会让手柄在 PC 上反复消失/出现（时连时断），所以两种动作都要求
    // 连续 WIRELESS_MODE_CONFIRM_PACKETS 个包报同一个模式才真的执行。
    if (!paired || mode != (uint8_t)opts.inputMode) {
        if (mode == pendingMode) {
            if (pendingModeCount < WIRELESS_MODE_CONFIRM_PACKETS) pendingModeCount++;
        } else {
            pendingMode = mode;
            pendingModeCount = 1;
        }
        if (pendingModeCount >= WIRELESS_MODE_CONFIRM_PACKETS) {
            if (!paired) {
                // first valid packet: pair, remember the mode, reboot into it
                opts.wirelessPaired = true;
                paired = true;
            }
            // sender switched input mode: reboot into the new mode
            opts.inputMode = (InputMode)mode;
            Storage::getInstance().save(true);
            sleep_ms(400); // let the deferred flash write finish
            System::reboot(System::BootMode::DEFAULT);
        }
        return;
    }
    pendingModeCount = 0; // 模式一致：清掉待确认计数

    // cache the received state
    rxButtons = pkt[2] | ((uint16_t)pkt[3] << 8);
    rxDpad = pkt[4];
    rxlx = pkt[5] | ((uint16_t)pkt[6] << 8);
    rxly = pkt[7] | ((uint16_t)pkt[8] << 8);
    rxrx = pkt[9] | ((uint16_t)pkt[10] << 8);
    rxry = pkt[11] | ((uint16_t)pkt[12] << 8);
    rxlt = pkt[13];
    rxrt = pkt[14];
    lastPacketTime = to_ms_since_boot(get_absolute_time());
}

void WirelessReceiverAddon::preprocess() {
    // 关键：addon 的 preprocess()/process() 在 GP2040::setup() 里
    // （getButtonMappedBootAction）就会被调用一次，而那一次早于
    // main.cpp 的 multicore_launch_core1() 和 run() 里的 tud_init()：
    //   * 碰 usb_hw（tud_disconnect）会锁死 APB 总线
    //   * 走配对 → save(true) → 50ms 后定时刷 flash → multicore_lockout 等 core1
    //     → core1 还没启动，永久卡死（整机黑屏 + USB 消失）
    // tud_inited() 为真 = 主循环已经跑起来，这一整套才是安全的。
    if (!tud_inited()) {
        return;
    }
    // 未配对时藏掉 USB 身份。注意 preprocess() 在 GP2040::setup() 的
    // getButtonMappedBootAction() 里也会被调用一次，那次早于 tud_init()——
    // 此时碰 usb_hw（dcd_disconnect 读写的是处于复位的 USB 控制器）会锁死总线，
    // 表现为整机黑屏 + USB 完全不出现。必须等 tud_inited() 之后再调。
    if (!paired && !usbHidden && tud_inited()) {
        usbHidden = true;
        tud_disconnect();
    }
    uint8_t pkt[NRF24_PAYLOAD];
    bool got = false;
    while (radio.readPacket(pkt)) {
        got = true;
        handlePacket(pkt);
    }
    // 看门狗：长时间无包则重新初始化射频，自动恢复卡死
    uint32_t now = to_ms_since_boot(get_absolute_time());
    if (!got && now - lastPacketTime > 1000 && now - lastRadioReinit > 3000) {
        lastRadioReinit = now;
        radio.begin(spi0, WIRELESS_RX_CSN_PIN, WIRELESS_RX_CE_PIN);
        radio.startListening();
    }
    // gamepad->read() clears the state every frame, so re-inject the cached
    // state each preprocess; release everything after 1000ms without a packet
    if (paired && now - lastPacketTime < 1000) {
        Gamepad *g = Storage::getInstance().GetGamepad();
        g->state.buttons = rxButtons;
        g->state.dpad = rxDpad;
        g->state.lx = rxlx;
        g->state.ly = rxly;
        g->state.rx = rxrx;
        g->state.ry = rxry;
        g->state.lt = rxlt;
        g->state.rt = rxrt;
    }
}

void WirelessReceiverAddon::process() {
    uint32_t now = to_ms_since_boot(get_absolute_time());
    bool packetsRecent = (now - lastPacketTime) < 1000;
#if WIRELESS_RX_RGB_LED_PIN >= 0
    if (now - lastLedToggle >= (paired ? 5000 : 300)) {
        lastLedToggle = now;
        if (paired) {
            rxNeoSetColor(0, 200, 0);      // 已配对：绿色常亮
        } else {
            ledOn = !ledOn;
            if (ledOn) {
                // 蓝色闪 = 收得到包但发送端一直在发 0xFF（没拿到 Pico 输入模式）
                // 红色闪 = 一个包都收不到（射频/供电/接线）
                rxNeoSetColor(packetsRecent ? 0 : 200, 0, packetsRecent ? 200 : 0);
            } else {
                rxNeo.Off();
            }
        }
    }
#else
    if (now - lastLedToggle >= (paired ? 5000 : 300)) {
        lastLedToggle = now;
        ledOn = !ledOn;
        gpio_put(WIRELESS_RX_LED_PIN, paired ? 1 : ledOn);
    }
#endif
}
