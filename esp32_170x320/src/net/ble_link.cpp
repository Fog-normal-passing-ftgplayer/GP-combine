#include "ble_link.h"

#include <NimBLEDevice.h>
#include <stdio.h>
#include <string.h>

// 调试出口（默认关）。onWrite/onSubscribe 是协议栈任务上下文，只能往这里塞格式化好的
// 短字符串，真正的串口输出由主循环那侧的 sink 决定。
static void (*dbgSink)(const char *) = nullptr;

void bleLinkSetDebugSink(void (*fn)(const char *)) { dbgSink = fn; }

static void dbgHex(const char *tag, const uint8_t *p, size_t n) {
  if (!dbgSink) return;
  char buf[160];
  int w = snprintf(buf, sizeof(buf), "%s n=%u:", tag, (unsigned)n);
  for (size_t i = 0; i < n && w > 0 && w < (int)sizeof(buf) - 4; i++)
    w += snprintf(buf + w, sizeof(buf) - (size_t)w, " %02X", p[i]);
  dbgSink(buf);
}

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
// 连续 notify 失败次数。对端没订阅 TX 时 notify 会一直返回 false，
// 无限重试就等于把 TX 永久卡死（txLen 永不为 0 → bleLinkSend 之后全被拒），
// 所以到阈值就把这一帧丢掉。
static uint8_t txFailStreak = 0;

static NimBLEServer          *srv    = nullptr;
static NimBLECharacteristic  *txChr  = nullptr;
// 文本模式自己组帧时用的 seq（十六进制文本是整帧照抄，用不到这个）。
// 递增一下，手机上看回包序号变了就知道是新一轮，不用靠时间猜。
static uint16_t textSeq = 0;
static bool  inited    = false;
static volatile bool enabled = false;   // 广播开着（开关状态）
static volatile int  clients = 0;       // 已连接手机数
static volatile bool authed  = false;   // 当前连接是否过了 AUTH
// **协商后**的实际 MTU（0 = 还不知道）。不能用 NimBLEDevice::getMTU() 顶替 ——
// 那个返回的是本机 setMTU(247) 设的期望值；手机要是只协商到 23，
// 按 244 切出来的分片会超出单次可发长度，notify 一直失败。
static volatile uint16_t connMtu = 0;

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
    connMtu = info.getMTU();          // 协商结果，之后由 onMTUChange 更新
    txLen = txOff = 0; txFailStreak = 0;   // 上一台手机没发完的半帧不要带过来
    if (dbgSink) {
      char b[64];
      snprintf(b, sizeof(b), "[ble] CONN t=%d mtu=%u", (int)info.getConnHandle(),
               (unsigned)connMtu);
      dbgSink(b);
    }
    // 配置助手是"点一下就改一下"，请求快一点的连接间隔（15–30 ms），不加 latency
    s->updateConnParams(info.getConnHandle(), 12, 24, 0, 200);
  }

  void onDisconnect(NimBLEServer *s, NimBLEConnInfo &, int) override {
    clients = (int)s->getConnectedCount();
    authed  = false;
    connMtu = 0;
    txLen = txOff = 0; txFailStreak = 0;   // 同上：半帧不能留给下一台手机
    if (enabled) NimBLEDevice::startAdvertising();   // 还开着开关就继续等下一台手机
  }

  void onMTUChange(uint16_t mtu, NimBLEConnInfo &) override { connMtu = mtu; }
};

class RxCb : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic *c, NimBLEConnInfo &) override {
    NimBLEAttValue v = c->getValue();
    dbgHex("[ble] WR", v.data(), v.size());   // 手机写进来的原始字节，最关键的证据
    // 手测便利：nRF Connect 的写入框默认 UTF-8，手敲的十六进制/命令词会以 ASCII 进来
    // （实测 "A5 5A 01 ..." 是 28 个字符）。先试着翻成帧；翻不出来就按原字节走，
    // 让收帧器自己丢掉 —— 二进制帧首字节 0xA5 不可打印，永远不会落进文本分支。
    uint8_t frame[PROTO_HEADER + PROTO_MAX_PAYLOAD + 2];
    size_t n = protoFromText(v.data(), v.size(), frame, sizeof(frame), textSeq);
    if (n) {
      textSeq++;
      dbgHex("[ble] WR->frame", frame, n);
      rxPush(frame, n);
    } else {
      rxPush(v.data(), v.size());
    }
  }
};

// 对端到底有没有订阅 TX —— 没订阅的时候 notify 会一直失败，
// 现象和"设备收到帧但装死"完全一样，所以必须单独打出来。
class TxCb : public NimBLECharacteristicCallbacks {
  void onSubscribe(NimBLECharacteristic *, NimBLEConnInfo &, uint16_t subValue) override {
    if (!dbgSink) return;
    char b[64];
    snprintf(b, sizeof(b), "[ble] SUB tx sub=%u", (unsigned)subValue);
    dbgSink(b);
  }
};

static SrvCb srvCb;
static RxCb  rxCb;
static TxCb  txCb;

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
  txChr->setCallbacks(&txCb);
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
  // NimBLE 默认允许 3 个连接，写死 disconnect(0) 只会踢掉其中一台
  for (uint16_t h : srv->getPeerDevices()) srv->disconnect(h);
  clients = (int)srv->getConnectedCount();
}

void bleLinkClearSession(void) {
  bleLinkDisconnectAll();
  authed = false;
  connMtu = 0;
  txLen = txOff = 0;
  txFailStreak = 0;
  rxParser.reset();
  uint16_t t = rxTail;                 // 清掉没处理完的残帧，别带到下次连接
  while (t != rxHead) { t = (uint16_t)((t + 1) % RX_RING); rxTail = t; }
}

void bleLinkEnable(bool on) {
  enabled = on;
  if (!inited) return;                 // 还没装协议栈（第一次开开关时才装）
  if (on) {
    NimBLEDevice::startAdvertising();
  } else {
    NimBLEDevice::stopAdvertising();
    bleLinkClearSession();
  }
}

void bleLinkTick(void) {
  if (txLen == 0) return;
  // 一次 tick 就把整帧吐完。netTick() 是「tick 一次 → 把收到的帧全处理掉」，
  // 如果这里只推一片，一个 loop 周期里连着收到两帧时，第二帧的回包会被
  // bleLinkSend 以「上一帧还没吐完」为由拒掉，然后就没有然后了。
  while (txOff < txLen) {
    size_t chunk = bleNotifyChunk(connMtu, txLen - txOff);
    if (!txChr || !txChr->notify(txBuf + txOff, chunk)) {
      if (dbgSink) {
        char b[80];
        snprintf(b, sizeof(b), "[ble] NOTIFY fail chunk=%u mtu=%u streak=%u",
                 (unsigned)chunk, (unsigned)connMtu, (unsigned)(txFailStreak + 1));
        dbgSink(b);
      }
      if (++txFailStreak >= 20) { txLen = txOff = 0; txFailStreak = 0; }
      return;                          // 下次 tick 再试
    }
    txFailStreak = 0;
    txOff += chunk;
  }
  txLen = txOff = 0;                   // 发完清空，下一帧重新开始
  if (dbgSink) dbgSink("[ble] SENT");
}

bool bleLinkPollRx(ProtoFrame &out) {
  size_t consumed = 0;
  while (rxTail != rxHead) {
    uint8_t b = rxRing[rxTail];
    rxTail = (uint16_t)((rxTail + 1) % RX_RING);
    consumed++;
    if (rxParser.push(b, out)) {
      // 走的字节比这一帧本身多 = 前面混了垃圾/半帧，收帧器是靠丢弃重新同步的
      size_t exact = (size_t)PROTO_HEADER + out.len + 2;
      if (dbgSink && consumed > exact) {
        char buf[64];
        snprintf(buf, sizeof(buf), "[ble] rx resync dropped=%u", (unsigned)(consumed - exact));
        dbgSink(buf);
      }
      return true;
    }
  }
  // 有字节进来但凑不出一整帧：写到了、但内容不是合法帧（长度/CRC 不符）
  if (consumed && dbgSink) {
    char buf[64];
    snprintf(buf, sizeof(buf), "[ble] rx partial bytes=%u", (unsigned)consumed);
    dbgSink(buf);
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
