#include "addons/uart_link.h"
#include "storagemanager.h"
#include "gamepad.h"
#include "system.h"
#include "hardware/adc.h"

#include "hardware/uart.h"
#include "hardware/gpio.h"
#include "hardware/flash.h"
#include "pico/multicore.h"
#include "pico/time.h"
#include "hardware/sync.h"
#include "CRC32.h"
#include "animationstation/animationstation.h"

bool UARTLinkAddon::inputMuted = false;

// ESP32 侧设置持久化：存在 Pico flash 顶部下方独立 4KB 扇区（避开 GP2040-CE 配置区）
#define ESP_CFG_XIP_ADDR  0x101F7000
#define ESP_CFG_FLASH_OFF 0x1F7000
#define ESP_CFG_MAGIC     0x43504745   // "EGPC"

struct EspCfgBlock {
    uint32_t magic;
    uint32_t crc;
    uint8_t data[16];
};

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
        configLedOff = get_absolute_time();   // 已过期 = 不占用指示灯
        espCfgValid = espCfgRead();
        initialized = true;
    }
}

bool UARTLinkAddon::espCfgRead() {
    const EspCfgBlock *blk = reinterpret_cast<const EspCfgBlock *>(ESP_CFG_XIP_ADDR);
    if (blk->magic != ESP_CFG_MAGIC) return false;
    if (blk->crc != CRC32::calculate(blk->data, 16)) return false;
    memcpy(espCfg, blk->data, 16);
    return true;
}

// 真正落盘。必须在“另一核已 lockout + 本核中断已关”的窗口里擦写：
// flash 操作期间 XIP 关闭，此时任何 flash 里的中断处理函数都会 hard fault。
// 以前这里是 alarm 回调，只 lockout 没关中断 —— 靠“所有 IRQ 同优先级”侥幸没炸，
// 一旦有驱动调高优先级（或换 RP2350）就会在保存设置时挂死。
void UARTLinkAddon::espCfgCommitNow() {
    // core1 还没 launch 时 lockout 会永久等待（FlashPROM 里踩过），先确认再动手。
    if (!multicore_lockout_victim_is_initialized(1)) {
        espCfgWriteDue = make_timeout_time_ms(50);
        return;
    }

    EspCfgBlock blk;
    blk.magic = ESP_CFG_MAGIC;
    blk.crc = CRC32::calculate(espCfg, 16);
    memcpy(blk.data, espCfg, 16);

    multicore_lockout_start_blocking();
    uint32_t interrupts = save_and_disable_interrupts();
    flash_range_erase(ESP_CFG_FLASH_OFF, FLASH_SECTOR_SIZE);
    flash_range_program(ESP_CFG_FLASH_OFF, reinterpret_cast<const uint8_t *>(&blk), FLASH_PAGE_SIZE);
    // 顺序和 FlashPROM 一致：先解除 lockout，再恢复中断。
    // 反过来会在“中断已开、lockout 还在”的窗口里被 FlashPROM 的 alarm 抢占，
    // 造成嵌套 lockout。
    multicore_lockout_end_blocking();
    restore_interrupts(interrupts);

    espCfgWritePending = false;
}

void UARTLinkAddon::espCfgScheduleWrite() {
    if (espCfgWritePending) return;   // 60ms 内的连续保存合并成一次
    espCfgWritePending = true;
    espCfgWriteDue = make_timeout_time_ms(60);
}

void UARTLinkAddon::sendEspConfigFrame(bool ok, const uint8_t *data) {
    uint8_t frame[23];
    frame[0] = LINK_FRAME_MAGIC;
    frame[1] = LINK_FRAME_VERSION;
    frame[2] = LINK_FRAME_TYPE_ESP_LOAD;
    frame[3] = 17; // ok(1) + data(16)
    frame[4] = ok ? 1 : 0;
    for (int i = 0; i < 16; i++) frame[5 + i] = data[i];
    uint16_t crc = 0xFFFF;
    for (int i = 1; i <= 20; i++) crc = crc16_update(crc, frame[i]);
    frame[21] = (uint8_t)(crc & 0xFF);
    frame[22] = (uint8_t)(crc >> 8);
    uart_write_blocking(uart0, frame, sizeof(frame));
}

void UARTLinkAddon::onEspSaveFrame(uint8_t *payload, uint8_t len) {
    if (len < 16) return;
    memcpy(espCfg, payload, 16);
    espCfgValid = true;
    espCfgScheduleWrite();
}

void UARTLinkAddon::onEspLoadReq() {
    sendEspConfigFrame(espCfgValid, espCfg);
}

void UARTLinkAddon::onMuteFrame(uint8_t *payload, uint8_t len) {
    if (len < 1) return;
    inputMuted = (payload[0] != 0);
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

// ---- GP-Combine: LED 状态与 CE AnimationProfile 模型的映射 ----
// combine 机内「灯光」页面是简化模型（单一动画 + 亮度 + 颜色 + 速度），
// CE 的 LED 重写后配置存在 AnimationOptions.profiles[baseProfileIndex] 里，
// 两者在这里对齐。上一级（ESP32）不做任何 LED 结构假设，只看这几个字节。
static int8_t ledProfileIndex(AnimationOptions &aOpts) {
    if (aOpts.profiles_count == 0) return -1;
    int8_t p = (int8_t)aOpts.baseProfileIndex;
    if (p < 0 || p >= (int8_t)aOpts.profiles_count) p = 0;
    return p;
}

static uint8_t ledProfileColorIndex(AnimationOptions &aOpts, int8_t p) {
    if (p < 0) return 1;
    const AnimationProfile &prof = aOpts.profiles[p];
    if (prof.notPressedStaticColors.size == 0) return 1;
    uint8_t idx = prof.notPressedStaticColors.bytes[0];
    return (idx < (uint8_t)colors.size()) ? idx : 1;
}

static uint32_t ledColorRGB(uint8_t index) {
    if (index >= colors.size()) index = 1; // fallback: white
    const RGB &c = colors[index];
    return ((uint32_t)c.r << 16) | ((uint32_t)c.g << 8) | c.b;
}

void UARTLinkAddon::sendStatusFrame(uint8_t socdMode, uint8_t dpadMode, uint8_t inputMode,
                                    uint8_t flags, uint8_t debounceDelay,
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

    // LED 状态直接从 CE 的配置模型读出来（不再维护 combine 的 ANIM_/COLOR_ 索引）
    AnimationOptions &aOpts = Storage::getInstance().getAnimationOptions();
    int8_t ledProfile = ledProfileIndex(aOpts);
    uint8_t ledEffect = (ledProfile >= 0) ? (uint8_t)aOpts.profiles[ledProfile].baseNonPressedEffect : 0;
    uint8_t ledColor = ledProfileColorIndex(aOpts, ledProfile);
    uint16_t ledCycle = (ledProfile >= 0) ? (uint16_t)aOpts.profiles[ledProfile].baseCycleTime : 0;
    frame[9] = ledEffect;
    frame[10] = (uint8_t)aOpts.brightness;
    frame[11] = ledColor;
    frame[12] = (uint8_t)(ledCycle & 0xFF);
    frame[13] = (uint8_t)(ledCycle >> 8);
    frame[14] = 0; // 旧固件的 rainbowCycle 槽位，CE 已并入 baseCycleTime
    frame[15] = 0;
    frame[16] = ledFlags;
    frame[17] = 0; // 旧固件的 flowCycle 槽位（CE 无“流水”特效）
    frame[18] = 0;
    frame[19] = (uint8_t)(battMv & 0xFF);
    frame[20] = (uint8_t)(battMv >> 8);
    frame[21] = battFlags;
    uint16_t crc = 0xFFFF;
    for (int i = 1; i <= 21; i++) crc = crc16_update(crc, frame[i]);
    frame[22] = (uint8_t)(crc & 0xFF);
    frame[23] = (uint8_t)(crc >> 8);
    uart_write_blocking(uart0, frame, sizeof(frame));
}

// LED 配置帧：字节含义见 headers/addons/uart_link.h 的 LINK_LED_* 说明。
// 帧长仍然是 10 字节，改变的是 payload 语义（旧固件的 CRC / 长度校验不受影响）。
void UARTLinkAddon::onLedConfigFrame(uint8_t *payload, uint8_t len) {
    if (len < 5) return;
    AnimationOptions &aOpts = Storage::getInstance().getAnimationOptions();
    LEDOptions &lOpts = Storage::getInstance().getLedOptions();

    // CE 的 LED 配置是按 profile 存的；机内页面只编辑“当前 profile”
    if (aOpts.profiles_count == 0) {
        aOpts.profiles_count = 1;
        aOpts.baseProfileIndex = 0;
    }
    int8_t p = ledProfileIndex(aOpts);
    if (p < 0) p = 0;
    AnimationProfile &prof = aOpts.profiles[p];

    uint8_t effect = payload[0];
    if (effect > LINK_LED_EFFECT_MAX) effect = 0;
    uint8_t colorIdx = payload[2];
    if (colorIdx >= (uint8_t)colors.size()) colorIdx = 1;
    uint8_t cycle = payload[4];
    if (cycle >= CYCLE_STEPS) cycle = CYCLE_STEPS - 1;

    prof.bEnabled = true;
    prof.baseNonPressedEffect = (AnimationNonPressedEffects)effect;
    prof.baseCycleTime = cycle;
    prof.nonPressedSpecialColor = ledColorRGB(colorIdx);
    // 静态色按灯位存“调色板索引”，这里把整条灯带刷成同一个索引
    memset(prof.notPressedStaticColors.bytes, colorIdx, sizeof(prof.notPressedStaticColors.bytes));
    prof.notPressedStaticColors.size = sizeof(prof.notPressedStaticColors.bytes);
    // 按下时保持同一颜色，行为与原固件「静态/追逐/彩虹按下不变色」一致
    prof.basePressedEffect = AnimationPressedEffects::AnimationPressedEffects_PRESSEDEFFECT_STATIC_COLOR;

    aOpts.brightness = payload[1];
    lOpts.turnOffWhenSuspended = (payload[3] & 0x01) != 0;

    Storage::getInstance().save(true);
    // CE 原生的重载路径：下一帧 LED 循环会 InitSettings() + configureLEDs()
    AnimationStation::getInstance().setRestartLeds(true);

    GamepadOptions &opts = Storage::getInstance().getGamepadOptions();
    sendStatusFrame((uint8_t)opts.socdMode, (uint8_t)opts.dpadMode, (uint8_t)opts.inputMode,
                    (opts.fourWayMode ? 0x01 : 0) | (opts.invertXAxis ? 0x02 : 0) |
                    (opts.invertYAxis ? 0x04 : 0), (uint8_t)opts.debounceDelay,
                    lOpts.turnOffWhenSuspended ? 0x01 : 0, battMv, battFlags);
}

void UARTLinkAddon::onConfigFrame(uint8_t *payload, uint8_t len) {
    if (len < 5) return;
    // 收到配置帧亮灯 0.8s 做提示。原来是 busy_wait_us(800000)：主循环整整停
    // 0.8 秒，既不发输入帧也不跑 tud_task()，接收端这 0.8 秒收到的是冻结的旧
    // 输入——看起来就是无线断了。改成记截止时刻，由 postprocess() 关灯。
    if (UART_LINK_LED_PIN >= 0) {
        gpio_put(UART_LINK_LED_PIN, 1);
        configLedOff = make_timeout_time_ms(800);
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
    LEDOptions &l2 = Storage::getInstance().getLedOptions();
    sendStatusFrame((uint8_t)o2.socdMode, (uint8_t)o2.dpadMode, (uint8_t)o2.inputMode,
                    (o2.fourWayMode ? 0x01 : 0) | (o2.invertXAxis ? 0x02 : 0) |
                    (o2.invertYAxis ? 0x04 : 0), (uint8_t)o2.debounceDelay,
                    l2.turnOffWhenSuspended ? 0x01 : 0, battMv, battFlags);
    if (inputChanged) {
        // 重启前把还没落盘的 ESP 镜像写完，否则 Pico flash 里留下旧镜像，
        // 下次开机会被 ESP32 当成“权威配置”覆盖掉刚存的设置在 LittleFS 里的值。
        if (espCfgWritePending) espCfgCommitNow();
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
        } else if (b == (uint8_t)(rxCrcCalc >> 8) &&
            rxCrcLo == (uint8_t)(rxCrcCalc & 0xFF) &&
            rxType == LINK_FRAME_TYPE_ESP_SAVE) {
            onEspSaveFrame(rxPayload, rxLen);
        } else if (b == (uint8_t)(rxCrcCalc >> 8) &&
            rxCrcLo == (uint8_t)(rxCrcCalc & 0xFF) &&
            rxType == LINK_FRAME_TYPE_ESP_LOAD_REQ) {
            onEspLoadReq();
        } else if (b == (uint8_t)(rxCrcCalc >> 8) &&
            rxCrcLo == (uint8_t)(rxCrcCalc & 0xFF) &&
            rxType == LINK_FRAME_TYPE_MUTE) {
            onMuteFrame(rxPayload, rxLen);
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

    // 输入帧放在 process()（gamepad->process() 之后、驱动发 USB 报告之前）发：
    // 原来在 postprocess()，要等 tud_task()/USB 处理完才发，白等一个周期。
    // 这里 GetGamepad() 的 state 已经过 MPGS，且 UARTLink 排在 Turbo/Macro 之后，
    // 与原来 GetProcessedGamepad() 看到的是同一份数据。
    Gamepad* g = Storage::getInstance().GetGamepad();
    if (g == nullptr) return;
    uint32_t now = to_ms_since_boot(get_absolute_time());
    uint16_t buttons = (uint16_t)(g->state.buttons & 0xFFFF);
    uint8_t dpad = (uint8_t)g->state.dpad;
    uint16_t lx = (uint16_t)g->state.lx, ly = (uint16_t)g->state.ly;
    uint16_t rx = (uint16_t)g->state.rx, ry = (uint16_t)g->state.ry;
    uint8_t lt = (uint8_t)g->state.lt, rt = (uint8_t)g->state.rt;
    // 摇杆 ADC 的 1LSB 抖动会让“任意变化”每圈都成立，把 921600 的 UART 打满；
    // UART 一满，ESP32 的 linkTask 就没有空闲、发包任务被饿死（实测 +2ms）。
    // 数字量（按键/十字键）仍然立即发；只有模拟量限到 1ms 一帧。
    bool digitalChanged = (buttons != lastButtons || dpad != lastDpad);
    bool analogChanged = (lx != lastLx || ly != lastLy || rx != lastRx || ry != lastRy ||
                          lt != lastLt || rt != lastRt);
    if (digitalChanged || (analogChanged && now - lastSent >= 1) || now - lastSent >= 50) {
        sendInputFrame(buttons, dpad, lx, ly, rx, ry, lt, rt);
        lastButtons = buttons;
        lastDpad = dpad;
        lastLx = lx; lastLy = ly; lastRx = rx; lastRy = ry;
        lastLt = lt; lastRt = rt;
        lastSent = now;
    }
}

void UARTLinkAddon::postprocess(bool sent) {
    if (!initialized) return;
    // 放在 postprocess（tud_task 之后）落盘：擦写期间主循环会停 ~50ms，
    // 此时本帧 USB 报告已经发出去，对有线输入的影响最小。
    if (espCfgWritePending && time_reached(espCfgWriteDue)) {
        espCfgCommitNow();
    }
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
    // 配置帧提示灯的常亮优先（见 onConfigFrame）
    if (UART_LINK_LED_PIN >= 0) {
        bool on = !time_reached(configLedOff) || (now - lastAckTime < 500);
        if (on != rxLedState) {
            rxLedState = on;
            gpio_put(UART_LINK_LED_PIN, on);
        }
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
    LEDOptions &lOpts = Storage::getInstance().getLedOptions();
    if (socdMode != lastSocdMode || dpadMode != lastDpadMode ||
        inputMode != lastInputMode || flags != lastFlags ||
        debounce != lastDebounce || now - lastStatusSent >= 1000) {
        sendStatusFrame(socdMode, dpadMode, inputMode, flags, debounce,
                        lOpts.turnOffWhenSuspended ? 0x01 : 0, battMv, battFlags);
        lastSocdMode = socdMode;
        lastDpadMode = dpadMode;
        lastInputMode = inputMode;
        lastFlags = flags;
        lastDebounce = debounce;
        lastStatusSent = now;
    }
}
