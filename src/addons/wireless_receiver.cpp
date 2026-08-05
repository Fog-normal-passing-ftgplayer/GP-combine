#include "addons/wireless_receiver.h"
#include "addons/nrf24.h"
#include "storagemanager.h"
#include "gamepad.h"
#include "system.h"
#include "tusb.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"

NRF24 radio;

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
    if (!paired) {
        tud_disconnect(); // no gamepad identity until paired
    }
    radio.startListening();

    gpio_init(WIRELESS_RX_LED_PIN);
    gpio_set_dir(WIRELESS_RX_LED_PIN, GPIO_OUT);
    gpio_put(WIRELESS_RX_LED_PIN, 0);
    lastLedToggle = 0;
    ledOn = false;
}

void WirelessReceiverAddon::handlePacket(const uint8_t *pkt) {
    uint8_t mode = pkt[0];
    GamepadOptions &opts = Storage::getInstance().getGamepadOptions();

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
    while (radio.readPacket(pkt)) {
        handlePacket(pkt);
    }
    // gamepad->read() clears the state every frame, so re-inject the cached
    // state each preprocess; release everything after 500ms without a packet
    uint32_t now = to_ms_since_boot(get_absolute_time());
    if (paired && now - lastPacketTime < 500) {
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
    if (now - lastLedToggle >= (paired ? 5000 : 300)) {
        lastLedToggle = now;
        ledOn = !ledOn;
        gpio_put(WIRELESS_RX_LED_PIN, paired ? 1 : ledOn);
    }
}
