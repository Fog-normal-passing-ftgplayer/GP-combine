#include "ble_link.h"

#include <NimBLEDevice.h>
#include <string.h>

// NUS：手机端（nRF Connect 或以后自己的 App）不用手写自定义服务也能直接连
static const char *UUID_SVC = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E";
static const char *UUID_RX  = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E";  // 手机 → 设备
static const char *UUID_TX  = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E";  // 设备 → 手机

// 收：协议栈任务（核 0）写、主循环（核 1）读，单生产者单消费者环形队列，不拿锁
#define RX_RING 512
static uint8_t rxRing[RX_RING];
static volatile uint16_t rxHead = 0, rxTail = 0;
static ProtoRx rxParser;

// 发：整帧先落 txBuf，bleLinkTick() 里按 MTU 一片一片发
static uint8_t txBuf[PROTO_HEADER + PROTO_MAX_PAYLOAD + 2];
static size_t  txLen = 0, txOff = 0;

static NimBLEServer          *srv    = nullptr;
static NimBLECharacteristic  *txChr  = nullptr;
static bool  inited    = false;
static volatile bool enabled = false;   // 广播开着（开关状态）
static volatile int  clients = 0;       // 已连接手机数
static volatile bool authed  = false;   // 当前连接是否过了 AUTH

static void rxPush(const uint8_t *p, size_t n) {
  for (size_t i = 0; i < n; i++) {
    uint16_t next = (uint16_t)((rxHead + 1) % RX_RING);
    if (next == rxTail) return;           // 满了就丢：宁可丢帧也不能卡住协议栈
    rxRing[rxHead] = p[i];
    rxHead = next;
  }
}

class SrvCb : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer *s, NimBLEConnInfo &info) override {
    clients = (int)s->getConnectedCount();
    authed  = false;
    // 配置助手是"点一下就改一下"，请求快一点的连接间隔（15–30 ms），不加 latency
    s->updateConnParams(info.getConnHandle(), 12, 24, 0, 200);
  }

  void onDisconnect(NimBLEServer *s, NimBLEConnInfo &, int) override {
    clients = (int)s->getConnectedCount();
    authed  = false;
    if (enabled) NimBLEDevice::startAdvertising();   // 还开着开关就继续等下一台手机
  }

  void onMTUChange(uint16_t, NimBLEConnInfo &) override {}
};

class RxCb : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic *c, NimBLEConnInfo &) override {
    NimBLEAttValue v = c->getValue();
    rxPush(v.data(), v.size());
  }
};

static SrvCb srvCb;
static RxCb  rxCb;

bool bleLinkBegin(const char *deviceName) {
  if (inited) return true;

  NimBLEDevice::init(deviceName);
  NimBLEDevice::setMTU(247);                  // 一帧基本一片发完
  srv = NimBLEDevice::createServer();
  if (!srv) return false;
  srv->setCallbacks(&srvCb);

  NimBLEService *svc = srv->createService(UUID_SVC);
  if (!svc) return false;
  txChr = svc->createCharacteristic(UUID_TX, NIMBLE_PROPERTY::NOTIFY);
  NimBLECharacteristic *rxChr =
      svc->createCharacteristic(UUID_RX, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::WRITE_NR);
  if (!txChr || !rxChr) return false;
  rxChr->setCallbacks(&rxCb);

  srv->start();

  NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
  adv->addServiceUUID(UUID_SVC);
  adv->setName(deviceName);
  adv->enableScanResponse(true);
  adv->setMinInterval(160);    // 100 ms
  adv->setMaxInterval(320);    // 200 ms：广播拉长，少占 2.4G 时间（nRF 那条虽已互斥，也别浪费）
  inited = true;
  return true;
}

void bleLinkDisconnectAll(void) {
  if (!srv) return;
  uint8_t n = srv->getConnectedCount();
  if (n) srv->disconnect(0);          // 最大连接数按 1 配，一个够用
  clients = (int)srv->getConnectedCount();
}

void bleLinkEnable(bool on) {
  enabled = on;
  if (!inited) return;                 // 还没装协议栈（第一次开开关时才装）
  if (on) {
    NimBLEDevice::startAdvertising();
  } else {
    NimBLEDevice::stopAdvertising();
    bleLinkDisconnectAll();
    authed = false;
    rxParser.reset();
    txLen = txOff = 0;
    uint16_t t = rxTail;               // 清掉没处理完的残帧，别带到下次连接
    while (t != rxHead) { t = (uint16_t)((t + 1) % RX_RING); rxTail = t; }
  }
}

void bleLinkTick(void) {
  if (txLen == 0) return;
  size_t chunk = NimBLEDevice::getMTU();
  chunk = (chunk > 3) ? (chunk - 3) : 20;
  if (chunk > txLen - txOff) chunk = txLen - txOff;
  if (txChr && txChr->notify(txBuf + txOff, chunk)) txOff += chunk;
  if (txOff >= txLen) txLen = txOff = 0;   // 发完清空，下一帧重新开始
}

bool bleLinkPollRx(ProtoFrame &out) {
  while (rxTail != rxHead) {
    uint8_t b = rxRing[rxTail];
    rxTail = (uint16_t)((rxTail + 1) % RX_RING);
    if (rxParser.push(b, out)) return true;
  }
  return false;
}

bool bleLinkSend(uint8_t cmd, uint16_t seq, const uint8_t *payload, uint16_t len) {
  if (!inited || clients <= 0) return false;
  if (txLen != 0) return false;                 // 上一帧还没吐完：让上层稍后重试
  size_t n = protoBuild(txBuf, sizeof(txBuf), cmd, seq, payload, len);
  if (!n) return false;
  txLen = n;
  txOff = 0;
  return true;
}

int  bleLinkState(void)   { if (!enabled) return 0; return clients > 0 ? 2 : 1; }
int  bleLinkClients(void) { return clients; }
bool bleLinkAdvertising(void) {
  if (!inited) return false;
  NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
  return adv && adv->isAdvertising();
}
bool bleLinkInited(void)  { return inited; }
bool bleLinkAuthed(void)  { return authed; }
void bleLinkSetAuthed(bool v) { authed = v; }
