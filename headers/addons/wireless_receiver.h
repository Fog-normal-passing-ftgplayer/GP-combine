#ifndef _WIRELESS_RECEIVER_H_
#define _WIRELESS_RECEIVER_H_

#include "gpaddon.h"
#include "BoardConfig.h"

#ifndef WIRELESS_RECEIVER_ENABLED
#define WIRELESS_RECEIVER_ENABLED 0
#endif

#ifndef WIRELESS_RX_CE_PIN
#define WIRELESS_RX_CE_PIN 6
#endif
#ifndef WIRELESS_RX_CSN_PIN
#define WIRELESS_RX_CSN_PIN 5
#endif
#ifndef WIRELESS_RX_SCK_PIN
#define WIRELESS_RX_SCK_PIN 2
#endif
#ifndef WIRELESS_RX_MOSI_PIN
#define WIRELESS_RX_MOSI_PIN 3
#endif
#ifndef WIRELESS_RX_MISO_PIN
#define WIRELESS_RX_MISO_PIN 4
#endif
#ifndef WIRELESS_RX_LED_PIN
#define WIRELESS_RX_LED_PIN 25
#endif
#ifndef WIRELESS_RX_RGB_LED_PIN
#define WIRELESS_RX_RGB_LED_PIN -1   // >=0 时用单颗 WS2812（如 RP2040-Zero 板载灯）当状态灯
#endif

// 配对 / 切输入模式都要写 flash + 重启；收到一个模式字节不对的包就立刻重启，
// 手柄会在 PC 上反复消失/出现（时连时断）。要求连续这么多包报同一个模式才动作。
// 发送端 1ms 一包 -> 约 20ms 确认，真实切模式感觉不到，抖动包会被挡住。
#ifndef WIRELESS_MODE_CONFIRM_PACKETS
#define WIRELESS_MODE_CONFIRM_PACKETS 20
#endif

class WirelessReceiverAddon : public GPAddon {
public:
    virtual bool available();
    virtual void setup();
    virtual void preprocess();
    virtual void process();
    virtual void postprocess(bool sent) {}
    virtual std::string name() { return "WirelessReceiverAddon"; }
    virtual void reinit() {}
private:
    void handlePacket(const uint8_t *pkt);
    bool paired;
    // cached state from the latest packet; re-injected every frame
    uint16_t rxButtons;
    uint8_t rxDpad;
    uint16_t rxlx, rxly, rxrx, rxry;
    uint8_t rxlt, rxrt;
    uint32_t lastPacketTime;
    uint32_t lastLedToggle;
    uint32_t lastRadioReinit;
    bool ledOn;
    bool usbHidden;
    uint8_t pendingMode;        // 去抖：正在确认的新输入模式
    uint8_t pendingModeCount;   // 连续报同一模式的包数
};

#endif
