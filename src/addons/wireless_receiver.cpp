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
    if (!paired) {
        tud_disconnect(); // no gamepad identity until paired
    }
    radio.startListening();

#if WIRELESS_RX_RGB_LED_PIN >= 0
    // RP2040-Zero 板载 WS2812 状态灯（pio1 空闲）
    rxNeo.Setup(WIRELESS_RX_RGB_LED_PIN, 1, LED_FORMAT_GRB, pio1, 0);
    rxNeo.Off();
#else
    gpio_init(WIRELESS_RX_LED_PIN);
    gpio_set_dir(WIRELESS_RX_LED_PIN, GPIO_OUT);
    gpio_put(WIRELESS_RX_LED_PIN, 0);
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

    if (!paired) {
        // first valid packet: pair, remember the mode, reboot into it
        opts.wirelessPaired = true;
        paired = true;
        opts.inputMode = (InputMode)mode;
        Storage::getInstance().save(true);
        sleep_ms(400); // let the deferred flash write finish
        System::reboot(System::BootMode::DEFAULT);
        return;
    }

    if (mode != (uint8_t)opts.inputMode) {
        // sender switched input mode: reboot into the new mode
        opts.inputMode = (InputMode)mode;
        Storage::getInstance().save(true);
        sleep_ms(400);
        System::reboot(System::BootMode::DEFAULT);
        return;
    }

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
#if WIRELESS_RX_RGB_LED_PIN >= 0
    if (now - lastLedToggle >= (paired ? 5000 : 300)) {
        lastLedToggle = now;
        if (paired) {
            rxNeoSetColor(0, 200, 0);      // 已配对：绿色常亮
        } else {
            ledOn = !ledOn;
            if (ledOn) {
                rxNeoSetColor(200, 0, 0);  // 未配对：红色闪烁
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
