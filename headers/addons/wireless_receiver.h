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
    bool ledOn;
};

#endif
