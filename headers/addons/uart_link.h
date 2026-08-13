#ifndef _UART_LINK_H_
#define _UART_LINK_H_

#include "gpaddon.h"
#include "BoardConfig.h"

#ifndef UART_LINK_ENABLED
#define UART_LINK_ENABLED 0
#endif

#ifndef UART_LINK_TX_PIN
#define UART_LINK_TX_PIN 0
#endif

#ifndef UART_LINK_RX_PIN
#define UART_LINK_RX_PIN 1
#endif

#ifndef UART_LINK_BAUD
#define UART_LINK_BAUD 921600
#endif

#ifndef UART_LINK_LED_PIN
#define UART_LINK_LED_PIN 25
#endif

#ifndef UART_LINK_USB_MV
#define UART_LINK_USB_MV 4300 // VSYS above this = USB powered (battery max ~4.2V)
#endif

// ---- frame protocol (shared with ESP32 side) ----
#define LINK_FRAME_MAGIC      0xAA
#define LINK_FRAME_VERSION    1
#define LINK_FRAME_TYPE_INPUT 0x01
#define LINK_FRAME_TYPE_ACK   0x02
#define LINK_FRAME_TYPE_STATUS 0x03
#define LINK_FRAME_TYPE_CONFIG 0x04
#define LINK_FRAME_TYPE_CONFIG_ACK 0x05
#define LINK_FRAME_TYPE_LED   0x06
#define LINK_FRAME_TYPE_ESP_SAVE 0x07      // ESP32 -> Pico: 保存 ESP32 侧设置
#define LINK_FRAME_TYPE_ESP_LOAD_REQ 0x08  // ESP32 -> Pico: 请求读取
#define LINK_FRAME_TYPE_ESP_LOAD 0x09      // Pico -> ESP32: 回传设置
#define LINK_FRAME_TYPE_MUTE 0x0A          // ESP32 -> Pico: 1=静音USB输入 0=恢复

class UARTLinkAddon : public GPAddon {
public:
    virtual bool available();
    virtual void setup();
    virtual void preprocess() {}
    virtual void process();
    virtual void postprocess(bool sent);
    virtual std::string name() { return "UARTLinkAddon"; }
    virtual void reinit() {}
    void espCfgCommitNow();   // 供 flash 写入定时回调调用
    static bool isInputMuted() { return inputMuted; }
private:
    void sendInputFrame(uint16_t buttons, uint8_t dpad,
                        uint16_t lx, uint16_t ly, uint16_t rx, uint16_t ry,
                        uint8_t lt, uint8_t rt);
    void sendStatusFrame(uint8_t socdMode, uint8_t dpadMode, uint8_t inputMode,
                         uint8_t flags, uint8_t debounceDelay,
                         uint8_t animIndex, uint8_t brightness, uint8_t staticColor,
                         uint16_t chaseCycle, uint16_t rainbowCycle, uint16_t flowCycle,
                         uint8_t ledFlags, uint16_t battMv, uint8_t battFlags);
    void onConfigFrame(uint8_t *payload, uint8_t len);
    void onLedConfigFrame(uint8_t *payload, uint8_t len);
    void onEspSaveFrame(uint8_t *payload, uint8_t len);
    void onEspLoadReq();
    void onMuteFrame(uint8_t *payload, uint8_t len);
    void sendEspConfigFrame(bool ok, const uint8_t *data);
    bool espCfgRead();
    void espCfgScheduleWrite();
    void handleRxByte(uint8_t b);
    bool initialized;
    uint32_t lastSent;
    uint16_t lastButtons;
    uint8_t lastDpad;
    uint16_t lastLx, lastLy, lastRx, lastRy;
    uint8_t lastLt, lastRt;
    uint32_t lastStatusSent;
    uint8_t lastSocdMode;
    uint8_t lastDpadMode;
    uint8_t lastInputMode;
    uint8_t lastFlags;
    uint8_t lastDebounce;
    uint16_t battMv;
    uint8_t battFlags;
    uint32_t lastBattSample;
    uint8_t rxState;    // 0 idle, 1 ver, 2 type, 3 len, 4 payload, 5 crcLo, 6 crcHi
    uint8_t rxType;
    uint8_t rxLen;
    uint8_t rxIdx;
    uint8_t rxPayload[16];
    uint16_t rxCrcCalc;
    uint8_t rxCrcLo;
    bool rxLedState;
    uint32_t lastAckTime;
    uint8_t espCfg[12] = {0};
    bool espCfgValid = false;
    volatile bool espCfgWritePending = false;
    static bool inputMuted;
};

#endif
