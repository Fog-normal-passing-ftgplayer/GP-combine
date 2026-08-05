#include "addons/uart_link.h"
#include "storagemanager.h"
#include "gamepad.h"
#include "system.h"
#include "hardware/adc.h"

#include "hardware/uart.h"
#include "hardware/gpio.h"
#include "pico/time.h"

// CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)
static uint16_t crc16_update(uint16_t crc, uint8_t b) {
    crc ^= (uint16_t)b << 8;
    for (int i = 0; i < 8; i++) {
        crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
    return crc;
}

bool UARTLinkAddon::available() {
    return UART_LINK_ENABLED;
}

void UARTLinkAddon::setup() {
    if (!initialized) {
        uart_init(uart0, UART_LINK_BAUD);
        gpio_set_function(UART_LINK_TX_PIN, GPIO_FUNC_UART);
        gpio_set_function(UART_LINK_RX_PIN, GPIO_FUNC_UART);
        gpio_set_pulls(UART_LINK_RX_PIN, true, false);

        // battery sense on GPIO29 (ADC3 = VSYS/3)
        adc_init();
        adc_gpio_init(29);

        if (UART_LINK_LED_PIN >= 0) {
            gpio_init(UART_LINK_LED_PIN);
            gpio_set_dir(UART_LINK_LED_PIN, GPIO_OUT);
            gpio_put(UART_LINK_LED_PIN, 0);
        }

        lastSent = 0;
        lastButtons = 0;
        lastDpad = 0;
        lastLx = 0; lastLy = 0; lastRx = 0; lastRy = 0;
        lastLt = 0; lastRt = 0;
        lastStatusSent = 0;
        lastSocdMode = 0xFF;
        lastDpadMode = 0xFF;
        lastInputMode = 0xFF;
        lastFlags = 0xFF;
        lastDebounce = 0xFF;
        battMv = 0;
        battFlags = 0;
        lastBattSample = 0;
        rxState = 0;
        rxType = 0;
        rxLen = 0;
        rxIdx = 0;
        rxCrcCalc = 0;
        rxCrcLo = 0;
        rxLedState = false;
        lastAckTime = 0;
        initialized = true;
    }
}

void UARTLinkAddon::sendInputFrame(uint16_t buttons, uint8_t dpad,
                                   uint16_t lx, uint16_t ly, uint16_t rx, uint16_t ry,
                                   uint8_t lt, uint8_t rt) {
    uint8_t frame[19];
    frame[0] = LINK_FRAME_MAGIC;
    frame[1] = LINK_FRAME_VERSION;
    frame[2] = LINK_FRAME_TYPE_INPUT;
    frame[3] = 13; // buttons(2) dpad(1) lx(2) ly(2) rx(2) ry(2) lt(1) rt(1)
    frame[4] = (uint8_t)(buttons & 0xFF);
    frame[5] = (uint8_t)(buttons >> 8);
    frame[6] = dpad;
    frame[7] = (uint8_t)(lx & 0xFF);
    frame[8] = (uint8_t)(lx >> 8);
    frame[9] = (uint8_t)(ly & 0xFF);
    frame[10] = (uint8_t)(ly >> 8);
    frame[11] = (uint8_t)(rx & 0xFF);
    frame[12] = (uint8_t)(rx >> 8);
    frame[13] = (uint8_t)(ry & 0xFF);
    frame[14] = (uint8_t)(ry >> 8);
    frame[15] = lt;
    frame[16] = rt;
    uint16_t crc = 0xFFFF;
    for (int i = 1; i <= 16; i++) crc = crc16_update(crc, frame[i]);
    frame[17] = (uint8_t)(crc & 0xFF);
    frame[18] = (uint8_t)(crc >> 8);
    uart_write_blocking(uart0, frame, sizeof(frame));
}

void UARTLinkAddon::sendStatusFrame(uint8_t socdMode, uint8_t dpadMode, uint8_t inputMode,
                                    uint8_t flags, uint8_t debounceDelay,
                                    uint8_t animIndex, uint8_t brightness, uint8_t staticColor,
                                    uint16_t chaseCycle, uint16_t rainbowCycle, uint16_t flowCycle,
                                    uint8_t ledFlags, uint16_t battMv, uint8_t battFlags) {
    uint8_t frame[24];
    frame[0] = LINK_FRAME_MAGIC;
    frame[1] = LINK_FRAME_VERSION;
    frame[2] = LINK_FRAME_TYPE_STATUS;
    frame[3] = 18; // gamepad + LED + battery status
    frame[4] = socdMode;
    frame[5] = dpadMode;
    frame[6] = inputMode;
    frame[7] = flags;
    frame[8] = debounceDelay;
    frame[9] = animIndex;
    frame[10] = brightness;
    frame[11] = staticColor;
    frame[12] = (uint8_t)(chaseCycle & 0xFF);
    frame[13] = (uint8_t)(chaseCycle >> 8);
    frame[14] = (uint8_t)(rainbowCycle & 0xFF);
    frame[15] = (uint8_t)(rainbowCycle >> 8);
    frame[16] = ledFlags;
    frame[17] = (uint8_t)(flowCycle & 0xFF);
    frame[18] = (uint8_t)(flowCycle >> 8);
    frame[19] = (uint8_t)(battMv & 0xFF);
    frame[20] = (uint8_t)(battMv >> 8);
    frame[21] = battFlags;
    uint16_t crc = 0xFFFF;
    for (int i = 1; i <= 21; i++) crc = crc16_update(crc, frame[i]);
    frame[22] = (uint8_t)(crc & 0xFF);
    frame[23] = (uint8_t)(crc >> 8);
    uart_write_blocking(uart0, frame, sizeof(frame));
}

void UARTLinkAddon::onLedConfigFrame(uint8_t *payload, uint8_t len) {
    if (len < 10) return;
    AnimationOptions &aOpts = Storage::getInstance().getAnimationOptions();
    LEDOptions &lOpts = Storage::getInstance().getLedOptions();
    aOpts.baseAnimationIndex = payload[0];
    aOpts.brightness = payload[1];
    aOpts.staticColorIndex = payload[2];
    lOpts.turnOffWhenSuspended = (payload[3] & 0x01) != 0;
    aOpts.chaseCycleTime = (uint32_t)(payload[4] | ((uint16_t)payload[5] << 8));
    aOpts.rainbowCycleTime = (uint32_t)(payload[6] | ((uint16_t)payload[7] << 8));
    aOpts.flowCycleTime = (uint32_t)(payload[8] | ((uint16_t)payload[9] << 8));

    Storage::getInstance().save(true);
    // report the new state immediately; the LED addon hot-swaps it live
    GamepadOptions &opts = Storage::getInstance().getGamepadOptions();
    sendStatusFrame((uint8_t)opts.socdMode, (uint8_t)opts.dpadMode, (uint8_t)opts.inputMode,
                    (opts.fourWayMode ? 0x01 : 0) | (opts.invertXAxis ? 0x02 : 0) |
                    (opts.invertYAxis ? 0x04 : 0), (uint8_t)opts.debounceDelay,
                    (uint8_t)aOpts.baseAnimationIndex, (uint8_t)aOpts.brightness,
                    (uint8_t)aOpts.staticColorIndex, (uint16_t)aOpts.chaseCycleTime,
                    (uint16_t)aOpts.rainbowCycleTime, (uint16_t)aOpts.flowCycleTime,
                    lOpts.turnOffWhenSuspended ? 0x01 : 0, battMv, battFlags);
}

void UARTLinkAddon::onConfigFrame(uint8_t *payload, uint8_t len) {
    if (len < 5) return;
    // solid LED ~0.8s: visible proof the config frame was received
    if (UART_LINK_LED_PIN >= 0) {
        gpio_put(UART_LINK_LED_PIN, 1);
        busy_wait_us(800000);
        gpio_put(UART_LINK_LED_PIN, 0);
    }
    GamepadOptions &options = Storage::getInstance().getGamepadOptions();
    uint8_t inputMode = payload[0];
    uint8_t socdMode = payload[1];
    uint8_t dpadMode = payload[2];
    uint8_t flags = payload[3];
    uint8_t debounce = payload[4];

    bool inputChanged = (inputMode != (uint8_t)options.inputMode);
    options.inputMode = (InputMode)inputMode;
    options.socdMode = (SOCDMode)socdMode;
    options.dpadMode = (DpadMode)dpadMode;
    options.fourWayMode = (flags & 0x01) != 0;
    options.invertXAxis = (flags & 0x02) != 0;
    options.invertYAxis = (flags & 0x04) != 0;
    options.debounceDelay = debounce;

    Storage::getInstance().save(true);
    // CONFIG_ACK: confirm the applied input mode back to the ESP32
    uint8_t ack[7];
    ack[0] = LINK_FRAME_MAGIC;
    ack[1] = LINK_FRAME_VERSION;
    ack[2] = LINK_FRAME_TYPE_CONFIG_ACK;
    ack[3] = 1;
    ack[4] = inputMode;
    uint16_t crc = 0xFFFF;
    for (int i = 1; i <= 4; i++) crc = crc16_update(crc, ack[i]);
    ack[5] = (uint8_t)(crc & 0xFF);
    ack[6] = (uint8_t)(crc >> 8);
    uart_write_blocking(uart0, ack, sizeof(ack));
    // report the new state immediately so the ESP32 can confirm
    GamepadOptions &o2 = Storage::getInstance().getGamepadOptions();
    AnimationOptions &a2 = Storage::getInstance().getAnimationOptions();
    LEDOptions &l2 = Storage::getInstance().getLedOptions();
    sendStatusFrame((uint8_t)o2.socdMode, (uint8_t)o2.dpadMode, (uint8_t)o2.inputMode,
                    (o2.fourWayMode ? 0x01 : 0) | (o2.invertXAxis ? 0x02 : 0) |
                    (o2.invertYAxis ? 0x04 : 0), (uint8_t)o2.debounceDelay,
                    (uint8_t)a2.baseAnimationIndex, (uint8_t)a2.brightness,
                    (uint8_t)a2.staticColorIndex, (uint16_t)a2.chaseCycleTime,
                    (uint16_t)a2.rainbowCycleTime, (uint16_t)a2.flowCycleTime,
                    l2.turnOffWhenSuspended ? 0x01 : 0, battMv, battFlags);
    if (inputChanged) {
        // FlashPROM::commit() defers the real flash write to a 50ms alarm;
        // give it time to finish before rebooting, otherwise the config is lost
        sleep_ms(400);
        // input mode is applied at boot by the driver, so reboot to switch
        System::reboot(System::BootMode::DEFAULT);
    }
}

void UARTLinkAddon::handleRxByte(uint8_t b) {
    switch (rxState) {
        case 0:
            if (b == LINK_FRAME_MAGIC) rxState = 1;
            break;
        case 1:
            rxCrcCalc = 0xFFFF;
            rxCrcCalc = crc16_update(rxCrcCalc, b);
            rxState = (b == LINK_FRAME_VERSION) ? 2 : 0;
            break;
        case 2:
            rxType = b;
            rxCrcCalc = crc16_update(rxCrcCalc, b);
            rxState = 3;
            break;
        case 3:
            rxLen = b;
            rxCrcCalc = crc16_update(rxCrcCalc, b);
            if (rxLen > sizeof(rxPayload)) { rxState = 0; break; }
            rxIdx = 0;
            rxState = (rxLen == 0) ? 5 : 4;
            break;
        case 4:
            rxPayload[rxIdx++] = b;
            rxCrcCalc = crc16_update(rxCrcCalc, b);
            if (rxIdx == rxLen) rxState = 5;
            break;
        case 5:
            rxCrcLo = b;
            rxState = 6;
            break;
    case 6:
        if (b == (uint8_t)(rxCrcCalc >> 8) &&
            rxCrcLo == (uint8_t)(rxCrcCalc & 0xFF) &&
            rxType == LINK_FRAME_TYPE_ACK) {
            rxLedState = true; // solid link-alive indicator, no flicker
            lastAckTime = to_ms_since_boot(get_absolute_time());
            if (UART_LINK_LED_PIN >= 0) gpio_put(UART_LINK_LED_PIN, 1);
        } else if (b == (uint8_t)(rxCrcCalc >> 8) &&
            rxCrcLo == (uint8_t)(rxCrcCalc & 0xFF) &&
            rxType == LINK_FRAME_TYPE_CONFIG) {
            onConfigFrame(rxPayload, rxLen);
        } else if (b == (uint8_t)(rxCrcCalc >> 8) &&
            rxCrcLo == (uint8_t)(rxCrcCalc & 0xFF) &&
            rxType == LINK_FRAME_TYPE_LED) {
            onLedConfigFrame(rxPayload, rxLen);
        }
        rxState = 0;
        break;
    }
}

void UARTLinkAddon::process() {
    if (!initialized) return;
    while (uart_is_readable(uart0)) {
        handleRxByte((uint8_t)uart_getc(uart0));
    }
}

void UARTLinkAddon::postprocess(bool sent) {
    if (!initialized) return;
    uint32_t now = to_ms_since_boot(get_absolute_time());
    // sample battery (VSYS/3 on GPIO29) and USB VBUS (GPIO24) every 500ms
    if (now - lastBattSample >= 500) {
        lastBattSample = now;
        adc_select_input(3);
        uint32_t sum = 0;
        for (int i = 0; i < 16; i++) sum += adc_read();
        uint16_t pinMv = (uint16_t)((sum / 16) * 3300UL / 4095);
        battMv = (uint16_t)((uint32_t)pinMv * 3); // VSYS = pin * 3
        battFlags = 0x01;                         // battery measurement valid
        // USB detection by voltage: VSYS above the battery range means USB VBUS
        // is feeding VSYS through the board diode
        if (battMv > UART_LINK_USB_MV) battFlags |= 0x02;
    }
    // keep the link LED solid while ACKs keep arriving, off after 500ms silence
    if (UART_LINK_LED_PIN >= 0) {
        bool on = (now - lastAckTime < 500);
        if (on != rxLedState) {
            rxLedState = on;
            gpio_put(UART_LINK_LED_PIN, on);
        }
    }

    Gamepad* g = Storage::getInstance().GetProcessedGamepad();
    if (g == nullptr) return;

    uint16_t buttons = (uint16_t)(g->state.buttons & 0xFFFF);
    uint8_t dpad = (uint8_t)g->state.dpad;
    uint16_t lx = (uint16_t)g->state.lx, ly = (uint16_t)g->state.ly;
    uint16_t rx = (uint16_t)g->state.rx, ry = (uint16_t)g->state.ry;
    uint8_t lt = (uint8_t)g->state.lt, rt = (uint8_t)g->state.rt;
    if (buttons != lastButtons || dpad != lastDpad ||
        lx != lastLx || ly != lastLy || rx != lastRx || ry != lastRy ||
        lt != lastLt || rt != lastRt || now - lastSent >= 50) {
        sendInputFrame(buttons, dpad, lx, ly, rx, ry, lt, rt);
        lastButtons = buttons;
        lastDpad = dpad;
        lastLx = lx; lastLy = ly; lastRx = rx; lastRy = ry;
        lastLt = lt; lastRt = rt;
        lastSent = now;
    }

    // report current mode status on change + 1s heartbeat so the ESP32 UI
    // always shows the real SOCD / dpad / input mode
    GamepadOptions options = Storage::getInstance().getGamepadOptions();
    uint8_t socdMode = (uint8_t)options.socdMode;
    uint8_t dpadMode = (uint8_t)options.dpadMode;
    uint8_t inputMode = (uint8_t)options.inputMode;
    uint8_t flags = (options.fourWayMode ? 0x01 : 0) |
                    (options.invertXAxis ? 0x02 : 0) |
                    (options.invertYAxis ? 0x04 : 0);
    uint8_t debounce = (uint8_t)options.debounceDelay;
    AnimationOptions &aOpts = Storage::getInstance().getAnimationOptions();
    LEDOptions &lOpts = Storage::getInstance().getLedOptions();
    if (socdMode != lastSocdMode || dpadMode != lastDpadMode ||
        inputMode != lastInputMode || flags != lastFlags ||
        debounce != lastDebounce || now - lastStatusSent >= 1000) {
        sendStatusFrame(socdMode, dpadMode, inputMode, flags, debounce,
                        (uint8_t)aOpts.baseAnimationIndex, (uint8_t)aOpts.brightness,
                        (uint8_t)aOpts.staticColorIndex, (uint16_t)aOpts.chaseCycleTime,
                        (uint16_t)aOpts.rainbowCycleTime, (uint16_t)aOpts.flowCycleTime,
                        lOpts.turnOffWhenSuspended ? 0x01 : 0, battMv, battFlags);
        lastSocdMode = socdMode;
        lastDpadMode = dpadMode;
        lastInputMode = inputMode;
        lastFlags = flags;
        lastDebounce = debounce;
        lastStatusSent = now;
    }
}
