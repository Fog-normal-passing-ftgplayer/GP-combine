#pragma once
// BLE 日志出口的环形队列。纯逻辑、不依赖 Arduino/FreeRTOS，主机侧能直接测
// （tools/host_tests）。设计约束来自 implementation-plan §2.1：
//
//   - `dbgSink` 会被 BLE 协议栈任务调用，**绝不能在回调里直接 notify**，只能入队；
//     真发帧由主循环 netTick 慢慢吐。
//   - 队列满就丢最旧的：日志永远不该阻塞主循环，也不该把协议栈拖慢。
//
// 行宽 96（含结尾 '\0'）是按"一条日志一行"定的：现在的 dbgPrintf 单行最长 160，
// 但真正要看的是 [ble]/[dbg]/[heap] 这几类短行；超长的直接截断，别为它把 24 KB
// 变成 40 KB。容量 256 行 ≈ 24 KB，够放"最近几分钟"。
//
// seq 的意义：每入队一行 total 自增 1，被丢弃的老行不会让 seq 回退。App 要"回放
// 最近 N 行"时，用 headSeq()..total()-1 这段区间逐行取，新日志继续涌进来也不会
// 把正在回放的那几行索引错位。

#include <stdint.h>
#include <stddef.h>
#include <string.h>

class LogQueue {
 public:
  static const int LOG_LINE_MAX = 96;

  // 绑定外部存储（不自己 malloc：这块内存固件侧按 PSRAM → 内部堆的顺序申请）
  void attach(char *storage, int lines) {
    m_buf = storage;
    m_cap = (storage != nullptr && lines > 0) ? lines : 0;
    m_head = 0;
    m_n = 0;
    m_dropped = 0;
    m_total = 0;
  }

  bool ready() const { return m_buf != nullptr && m_cap > 0; }
  int size() const { return m_n; }
  int capacity() const { return m_cap; }
  uint32_t dropped() const { return m_dropped; }

  uint64_t total() const { return m_total; }                      // 累计入队行数
  uint64_t headSeq() const { return m_total - (uint64_t)m_n; }    // 队首那行的 seq

  // 入队。len 传 0 表示按 C 字符串算长度。超长截断，满则丢最旧。
  void push(const char *s, size_t len = 0) {
    if (!ready() || s == nullptr) return;
    if (len == 0) len = strlen(s);
    if (len > (size_t)(LOG_LINE_MAX - 1)) len = (size_t)(LOG_LINE_MAX - 1);

    if (m_n == m_cap) {                 // 满了：挤掉最旧那行
      m_head = (m_head + 1) % m_cap;
      m_n--;
      m_dropped++;
    }
    char *dst = m_buf + (size_t)((m_head + m_n) % m_cap) * LOG_LINE_MAX;
    if (len) memcpy(dst, s, len);
    dst[len] = '\0';
    m_n++;
    m_total++;
  }

  bool peek(char *out) const {
    if (m_n == 0 || out == nullptr) return false;
    memcpy(out, m_buf + (size_t)m_head * LOG_LINE_MAX, LOG_LINE_MAX);
    return true;
  }

  bool pop(char *out) {
    if (!peek(out)) return false;
    m_head = (m_head + 1) % m_cap;
    m_n--;
    return true;
  }

  // 丢掉 seq 之前的行（回放窗口之外的陈货），返回丢掉的行数。
  // 只挪队首下标，不搬数据。
  int dropBefore(uint64_t seq) {
    uint64_t h = headSeq();
    if (seq <= h || m_n == 0) return 0;
    if (seq >= m_total) {
      int d = m_n;
      m_head = (m_head + m_n) % m_cap;
      m_n = 0;
      return d;
    }
    int d = (int)(seq - h);
    m_head = (int)(((uint64_t)m_head + (uint64_t)d) % (uint64_t)m_cap);
    m_n -= d;
    return d;
  }

  // 按 seq 取（回放用）。已被挤掉或还没写到的 seq 返回 false。
  bool peekSeq(uint64_t seq, char *out) const {
    if (out == nullptr || m_n == 0) return false;
    uint64_t h = headSeq();
    if (seq < h || seq >= m_total) return false;
    size_t idx = (size_t)((uint64_t)m_head + (seq - h)) % (size_t)m_cap;
    memcpy(out, m_buf + idx * LOG_LINE_MAX, LOG_LINE_MAX);
    return true;
  }

 private:
  char    *m_buf = nullptr;
  int      m_cap = 0;
  int      m_head = 0;      // 队首下标
  int      m_n = 0;         // 当前行数
  uint32_t m_dropped = 0;   // 被挤掉的行数（App 里显示"丢了 N 行"）
  uint64_t m_total = 0;     // 累计入队行数
};
