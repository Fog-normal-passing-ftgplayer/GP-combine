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
  CMD_CFG_GET   = 0x10,   // 17 字节设置镜像
  CMD_CFG_SET   = 0x11,   // 17 字节设置镜像
  CMD_CFG_RESET = 0x12,   // 恢复默认
  CMD_ERR       = 0x7F,   // 错误码 + 文本
};

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
