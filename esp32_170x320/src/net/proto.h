#pragma once
// GP-Combine 手机 App 协议：帧编解码（BLE 控制面与以后的 WiFi 数据面共用一套）
// 规范见 docs/superpowers/specs/2026-09-18-phone-app-design.md §5.1
//
//   偏移 0   2  魔数 0xA5 0x5A
//   偏移 2   1  协议版本 = 1
//   偏移 3   1  命令码
//   偏移 4   2  序号 seq（小端，回包原样带回）
//   偏移 6   2  载荷长度 len（小端）
//   偏移 8   n  载荷
//   末尾     2  CRC16-CCITT（覆盖 ver..载荷末尾，小端）
//
// 纯头文件、不依赖 Arduino：主机侧也能拿同一份代码跑单元测试。

#include <stdint.h>
#include <stddef.h>
#include <string.h>

#define PROTO_MAGIC0 0xA5u
#define PROTO_MAGIC1 0x5Au
#define PROTO_VERSION 1u
#define PROTO_HEADER 8u
#define PROTO_MAX_PAYLOAD 256u   // BLE 单帧载荷上限；大文件走 WiFi，不占这里

enum proto_cmd : uint8_t {
  CMD_PING      = 0x01,   // 任意载荷，原样回
  CMD_AUTH      = 0x02,   // 6 位配对码（ASCII）→ 1 字节结果
  CMD_INFO      = 0x03,   // 固件/分区/存储/内存
  CMD_PAIR_INFO = 0x04,   // 配对码、蓝牙开关、已连接手机数、热点状态
  CMD_LOG_SUB   = 0x06,   // 日志订阅：1 字节 mode（0 关 / 1 开 / 2 开+回放），可选第 2 字节回放行数
  CMD_CFG_GET   = 0x10,   // 17 字节设置镜像
  CMD_CFG_SET   = 0x11,   // 17 字节设置镜像
  CMD_CFG_RESET = 0x12,   // 恢复默认
  CMD_CFG_APPLY = 0x13,   // 17 字节设置镜像：只应用不落盘（拖滑条时的实时下发）
  CMD_GP_GET    = 0x20,   // → 5 字节手柄设置（布局见 pad_cfg.h）
  CMD_GP_SET    = 0x21,   // 5 字节手柄设置：应用 + 推给 Pico（Pico 侧自己落盘）
  CMD_LED_GET   = 0x22,   // → 7 字节灯光设置
  CMD_LED_SET   = 0x23,   // 7 字节灯光设置
  // 0x24 空着：蓝牙状态复用 0x04 PAIR_INFO（那串文本已经带了 name/pair/bt/clients/link）
  CMD_BT_SET    = 0x25,   // 改设备名 / 配对码 / 蓝牙开关（见 ProtoBtSet）
  CMD_BT_CLEAR  = 0x26,   // 重新生成配对码 → 回 6 位新码，然后断开所有手机
  CMD_PROF_LIST = 0x27,   // → PROF_SLOTS × 23 字节配置档记录（布局见 profiles.h）
  CMD_PROF_SAVE = 0x28,   // [档位][名字长][名字]：把设备当前设置存进该档
  CMD_PROF_LOAD = 0x29,   // [档位]：加载该档（应用 + 落盘）
  CMD_PROF_DEL  = 0x2A,   // [档位]：删除该档
  CMD_PROF_RENAME = 0x2B, // [档位][名字长][名字]：只改名字，**不动**档里存着的那份设置
  CMD_ERR       = 0x7F,   // 错误码 + 文本

  // 0x80 以上是"设备主动推"，不带 seq（固定 0），App 侧不能拿它等回包。
  CMD_LOG_EVT   = 0x86,   // 1 字节等级 + 文本（一行日志）
};

// ---- CMD_BT_SET 载荷 ----
// 0      flags：bit0 改名字 / bit1 改配对码 / bit2 改蓝牙开关
// 1      开关值（0/1，只有 bit2 置位时才算数）
// 2      名字长度 0..PROTO_NAME_MAX
// 3..    名字（UTF-8）
// 之后   配对码长度 + 配对码（ASCII，正好 6 位数字）
#define PROTO_BT_SET_NAME 0x01u
#define PROTO_BT_SET_PAIR 0x02u
#define PROTO_BT_SET_SW   0x04u
#define PROTO_NAME_MAX 20u

struct ProtoBtSet {
  uint8_t flags;
  uint8_t sw;
  uint8_t nameLen;
  char    name[PROTO_NAME_MAX + 1];
  uint8_t pairLen;
  char    pair[8];
};

// 任何一处对不上就整帧拒绝：改设备名/换配对码是不可逆动作，宁可报错让 App 重发。
static inline bool protoParseBtSet(const uint8_t *p, uint16_t len, ProtoBtSet &out) {
  if (p == nullptr || len < 3) return false;
  out.flags = p[0];
  if (out.flags & ~(PROTO_BT_SET_NAME | PROTO_BT_SET_PAIR | PROTO_BT_SET_SW)) return false;
  if (out.flags == 0) return false;                 // 什么都没说要改，别回个空洞的成功
  out.sw = p[1] ? 1 : 0;
  out.nameLen = p[2];
  if (out.nameLen > PROTO_NAME_MAX) return false;
  size_t off = 3;
  if ((size_t)len < off + out.nameLen + 1) return false;
  if ((out.flags & PROTO_BT_SET_NAME) && out.nameLen == 0) return false;
  memcpy(out.name, p + off, out.nameLen);
  out.name[out.nameLen] = '\0';
  off += out.nameLen;

  out.pairLen = p[off++];
  if ((size_t)len < off + out.pairLen) return false;
  if ((out.flags & PROTO_BT_SET_PAIR)) {
    if (out.pairLen != 6) return false;              // 配对码就是 6 位，多了少了都是发错
    for (uint8_t i = 0; i < 6; i++)
      if (p[off + i] < '0' || p[off + i] > '9') return false;
  }
  if (out.pairLen > sizeof(out.pair) - 1) return false;
  memcpy(out.pair, p + off, out.pairLen);
  out.pair[out.pairLen] = '\0';
  return true;
}

// ---- CMD_PROF_SAVE 载荷：[档位][名字长][名字] ----
struct ProtoProfSave {
  uint8_t slot;
  uint8_t nameLen;
  char    name[PROTO_NAME_MAX + 1];
};

static inline bool protoParseProfSave(const uint8_t *p, uint16_t len, ProtoProfSave &out) {
  if (p == nullptr || len < 2) return false;
  out.slot = p[0];
  out.nameLen = p[1];
  if (out.nameLen > PROTO_NAME_MAX) return false;
  if ((size_t)len < (size_t)2 + out.nameLen) return false;
  memcpy(out.name, p + 2, out.nameLen);
  out.name[out.nameLen] = '\0';
  return true;
}

// CMD_LOG_SUB 的载荷。mode 2 = 打开并把最近 replay 行回放一遍（默认 14 行）。
struct ProtoLogSub {
  uint8_t mode;
  uint8_t replay;
};

static inline bool protoParseLogSub(const uint8_t *p, uint16_t len, ProtoLogSub &out) {
  if (len < 1 || p == nullptr) return false;
  if (p[0] > 2u) return false;
  out.mode = p[0];
  out.replay = (len >= 2) ? p[1] : (uint8_t)14;
  if (out.replay == 0) out.replay = 14;   // 0 行回放没有意义，按默认走
  return true;
}

enum proto_err : uint8_t {
  ERR_OK          = 0x00,
  ERR_BAD_CRC     = 0x01,
  ERR_BAD_LEN     = 0x02,
  ERR_UNKNOWN_CMD = 0x03,
  ERR_NOT_AUTHED  = 0x04,
  ERR_BAD_ARG     = 0x05,
  ERR_NO_MEM      = 0x06,
  ERR_IO          = 0x07,
};

static inline uint16_t protoCrc16(const uint8_t *p, size_t n) {
  uint16_t crc = 0xFFFF;
  while (n--) {
    crc ^= (uint16_t)(*p++) << 8;
    for (int i = 0; i < 8; i++)
      crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
  }
  return crc;
}

struct ProtoFrame {
  uint8_t  cmd;
  uint16_t seq;
  uint16_t len;
  uint8_t  payload[PROTO_MAX_PAYLOAD];
};

// ---- 文本模式：把可打印 ASCII 的写入当成帧收 ----
//
// 起因（真机实测）：nRF Connect 的写入框默认是 UTF-8，手敲的十六进制会原样以 ASCII
// 发过来 —— 日志里就是 `WR n=28: 41 35 20 35 41 ...`（"A5 5A 01 ..." 的字符码）。
// 设备侧按二进制收帧只能静默丢掉，现象和「设备死了」一模一样；而各个 App 版本把
// 「UTF-8 / BYTE ARRAY」的切换入口放在哪都不一样，找它比改固件还费劲。
//
// 所以设备端两种都认。只有**整段都是可打印字符**才走文本分支，二进制帧首字节是 0xA5，
// 落不进这个条件，不会互相干扰。两条规则：
//   1) 十六进制字节串（空格/逗号随便有没有，也接受 0x 前缀）→ 这些字节就是整帧
//   2) 命令词：PING / INFO / PAIR / CFG / RESET / AUTH <6位数字>
//
// 返回整帧长度；0 = 认不出来，调用方应当按原字节喂给收帧器（让它自然丢掉）。
static inline size_t protoBuild(uint8_t *out, size_t outCap, uint8_t cmd, uint16_t seq,
                                const uint8_t *payload, uint16_t len);

static inline int protoIsTextSpace(uint8_t c) {
  return c == ' ' || c == '\t' || c == '\r' || c == '\n' || c == ',';
}

static inline int protoHexVal(uint8_t c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

static inline size_t protoFromText(const uint8_t *s, size_t n, uint8_t *out, size_t outCap,
                                   uint16_t seq) {
  if (!n) return 0;
  for (size_t i = 0; i < n; i++)
    if (s[i] < 0x20 || s[i] > 0x7E) return 0;   // 有不可打印字节 → 不是文本

  size_t b = 0, e = n;
  while (b < e && protoIsTextSpace(s[b])) b++;
  while (e > b && protoIsTextSpace(s[e - 1])) e--;
  if (b >= e) return 0;

  // 规则 1：十六进制。边扫边拼，不留中间缓冲（一帧最长 266 字节，堆栈上放不下 532 个字符）
  size_t total = 0;
  int hi = -1;
  bool hexOk = true;
  for (size_t i = b; i < e;) {
    uint8_t c = s[i];
    if (protoIsTextSpace(c)) { i++; continue; }
    if (c == '0' && i + 1 < e && (s[i + 1] == 'x' || s[i + 1] == 'X')) {
      if (hi >= 0) { hexOk = false; break; }    // "0x" 只能出现在字节开头
      i += 2; continue;
    }
    int hv = protoHexVal(c);
    if (hv < 0) { hexOk = false; break; }
    if (hi < 0) { hi = hv; i++; continue; }
    if (total >= outCap) { hexOk = false; break; }
    out[total++] = (uint8_t)((hi << 4) | hv);
    hi = -1;
    i++;
  }
  if (hexOk && hi < 0 && total > 0) return total;   // 半字节落单 = 不是十六进制串

  // 规则 2：命令词。取第一个词（不分大小写），最多 7 个字符
  size_t p = b;
  while (p < e && !protoIsTextSpace(s[p])) p++;
  char word[8];
  size_t wl = p - b;
  if (wl == 0 || wl >= sizeof(word)) return 0;
  for (size_t i = 0; i < wl; i++)
    word[i] = (char)((s[b + i] >= 'a' && s[b + i] <= 'z') ? s[b + i] - 32 : s[b + i]);
  word[wl] = '\0';

  uint8_t cmd;
  if      (!strcmp(word, "PING"))  cmd = CMD_PING;
  else if (!strcmp(word, "INFO"))  cmd = CMD_INFO;
  else if (!strcmp(word, "PAIR"))  cmd = CMD_PAIR_INFO;
  else if (!strcmp(word, "CFG"))   cmd = CMD_CFG_GET;
  else if (!strcmp(word, "RESET")) cmd = CMD_CFG_RESET;
  else if (!strcmp(word, "GP"))    cmd = CMD_GP_GET;
  else if (!strcmp(word, "LED"))   cmd = CMD_LED_GET;
  else if (!strcmp(word, "BT"))    cmd = CMD_PAIR_INFO;   // 蓝牙页的 name/pair/开关/连接数
  else if (!strcmp(word, "PROF"))  cmd = CMD_PROF_LIST;
  else if (!strcmp(word, "AUTH"))  cmd = CMD_AUTH;
  else return 0;

  if (cmd != CMD_AUTH) {
    // 后面不该再有多余的词："PING PONG" 这种是发错了，别猜用户想说什么
    for (size_t i = p; i < e; i++)
      if (!protoIsTextSpace(s[i])) return 0;
    return protoBuild(out, outCap, cmd, seq, nullptr, 0);
  }

  // AUTH 后面必须紧跟正好 6 位数字，多的少的都算发错，别猜
  size_t q = p;
  while (q < e && protoIsTextSpace(s[q])) q++;
  size_t r = e;
  while (r > q && protoIsTextSpace(s[r - 1])) r--;
  if (r - q != 6) return 0;
  for (size_t i = q; i < r; i++)
    if (s[i] < '0' || s[i] > '9') return 0;
  return protoBuild(out, outCap, cmd, seq, s + q, 6);
}

// 组帧。返回整帧长度；0 = 载荷超限或缓冲不够
static inline size_t protoBuild(uint8_t *out, size_t outCap, uint8_t cmd, uint16_t seq,
                                const uint8_t *payload, uint16_t len) {
  if (len > PROTO_MAX_PAYLOAD) return 0;
  size_t total = PROTO_HEADER + (size_t)len + 2;
  if (total > outCap) return 0;
  out[0] = PROTO_MAGIC0;
  out[1] = PROTO_MAGIC1;
  out[2] = PROTO_VERSION;
  out[3] = cmd;
  out[4] = (uint8_t)(seq & 0xFF);
  out[5] = (uint8_t)(seq >> 8);
  out[6] = (uint8_t)(len & 0xFF);
  out[7] = (uint8_t)(len >> 8);
  if (len) memcpy(out + PROTO_HEADER, payload, len);
  uint16_t crc = protoCrc16(out + 2, (size_t)PROTO_HEADER - 2 + (size_t)len);  // ver..载荷
  out[PROTO_HEADER + len]     = (uint8_t)(crc & 0xFF);
  out[PROTO_HEADER + len + 1] = (uint8_t)(crc >> 8);
  return total;
}

// 增量收帧器：一个字节一个字节喂，攒够一整帧且 CRC 对才吐出来。
// 坏字节直接丢，靠 0xA5 0x5A 重新同步（BLE 上不会粘包，但坏了要能自愈）。
class ProtoRx {
 public:
  void reset() { m_have = 0; }

  bool push(uint8_t b, ProtoFrame &out) {
    if (m_have >= sizeof(m_buf)) dropFront(1);   // 缓冲满（理论到不了）：丢掉最老的继续
    m_buf[m_have++] = b;
    return tryParse(out);
  }

 private:
 uint8_t m_buf[PROTO_HEADER + PROTO_MAX_PAYLOAD + 2];
  size_t  m_have = 0;

  void dropFront(size_t n) {
    memmove(m_buf, m_buf + n, m_have - n);
    m_have -= n;
  }

  // 只认队首那一帧。魔数/长度/CRC 任何一处不对，就把队首挪掉一格重新找 —— 
  // 这样前面混进垃圾字节（或半个残帧）也能自己走回来，不会把后面一整帧吃掉。
  bool tryParse(ProtoFrame &out) {
    for (;;) {
      if (m_have < 2) return false;
      if (m_buf[0] != PROTO_MAGIC0 || m_buf[1] != PROTO_MAGIC1) { dropFront(1); continue; }
      if (m_have < PROTO_HEADER) return false;
      // 版本不对就当垃圾丢掉重找。今天只有 ver=1，看着多余；哪天改了布局，
      // 少了这一句就是「新 App 发新布局，旧固件照老布局解析并执行命令」。
      if (m_buf[2] != PROTO_VERSION) { dropFront(1); continue; }

      uint16_t len = (uint16_t)(m_buf[6] | ((uint16_t)m_buf[7] << 8));
      if (len > PROTO_MAX_PAYLOAD) { dropFront(1); continue; }
      size_t total = PROTO_HEADER + (size_t)len + 2;
      if (m_have < total) return false;        // 这一帧还没收完

      uint16_t crcRx   = (uint16_t)(m_buf[total - 2] | ((uint16_t)m_buf[total - 1] << 8));
      uint16_t crcCalc = protoCrc16(m_buf + 2, (size_t)PROTO_HEADER - 2 + (size_t)len);
      if (crcRx != crcCalc) { dropFront(1); continue; }

      out.cmd = m_buf[3];
      out.seq = (uint16_t)(m_buf[4] | ((uint16_t)m_buf[5] << 8));
      out.len = len;
      if (len) memcpy(out.payload, m_buf + PROTO_HEADER, len);
      dropFront(total);
      return true;
    }
  }
};
