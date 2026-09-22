// 主机侧回归测试：只测「纯逻辑」，不重写被测代码。
// 教训：上个花屏 bug 是分块写缓冲漏了块内偏移，当时的主机测试是自己又写了一遍
// 循环去比对的，所以真代码坏了测试照样过。这里一律 include 固件用的那份头文件。
//
// 跑法：tools/host_tests/run.sh

#include <cstdio>
#include <cstring>
#include <string>

#include "../../esp32_170x320/src/nes_path.h"
#include "../../esp32_170x320/src/net/ble_link.h"
#include "../../esp32_170x320/src/net/log_queue.h"

static int failures = 0;

#define CHECK(cond, ...)                                                        \
  do {                                                                          \
    if (!(cond)) {                                                              \
      ++failures;                                                               \
      std::printf("FAIL %s:%d  ", __FILE__, __LINE__);                          \
      std::printf(__VA_ARGS__);                                                 \
      std::printf("\n");                                                        \
    }                                                                           \
  } while (0)

// ---- NES ROM 路径拼接 ----
// 同一个坑踩过两次：名字存全了，拼路径的 buf 没跟着变大 → open 不存在的路径 →
// 用户看到的是「按 A 启动游戏没反应」。
static void test_nes_path() {
  // 用「能存下的最长名字」当输入：比短文件名更能压到边界。
  // 真实例子："Super Mario Bros 3 (U) (PRG1) [!].nes" 这种在卡里很常见。
  std::string stem = "Super Mario Bros 3 (U) (PRG1) [!] (Shadow of the Ninja Hack)";
  while (stem.size() < (size_t)NES_ROM_NAME_MAX - 1 - 4) stem += "x";  // 留出 ".nes"
  std::string longest = stem + ".nes";
  CHECK(longest.size() == (size_t)NES_ROM_NAME_MAX - 1,
        "测试夹具长度 %zu，应该正好是 %d", longest.size(), NES_ROM_NAME_MAX - 1);

  char path[NES_ROM_PATH_MAX];
  int n = nesBuildRomPath(path, sizeof path, longest.c_str());

  CHECK(n > 0, "nesBuildRomPath 返回 %d", n);
  CHECK((size_t)n < sizeof path, "路径被截断了：需要 %d 字节，缓冲只有 %zu", n, sizeof path);
  CHECK(std::strncmp(path, "/nes/", 5) == 0, "前缀不对：%s", path);
  CHECK(std::strlen(path) == (size_t)n, "实际长度 %zu != 返回值 %d", std::strlen(path), n);
  // 截断最典型的症状就是结尾被啃掉，所以结尾必须还在
  CHECK(std::string(path).find(".nes") != std::string::npos, "扩展名被截掉了：%s", path);
  CHECK(std::string(path) == "/nes/" + longest, "拼出来的路径和期望不一致");

  // 旧实现用的是 80 字节局部缓冲：这条钉住它确实是坏的，
  // 顺便保证 fixture 真的能触发截断（否则上面那条测试就是假绿）。
  char small[80];
  int sn = nesBuildRomPath(small, sizeof small, longest.c_str());
  CHECK((size_t)sn >= sizeof small, "80 字节缓冲没截断（夹具不够长），测试无效");
}

// ---- BLE 分片大小 ----
// 分片必须按**协商后**的 MTU 算。用期望 MTU(247) 去给只协商到 23 的连接发 244 字节，
// notify 会一直失败 → txOff 不前进 → 回包永久卡死。
static void test_ble_chunk() {
  CHECK(bleNotifyChunk(247, 250) == 244, "MTU=247 应该切 244，得到 %zu", bleNotifyChunk(247, 250));
  CHECK(bleNotifyChunk(23, 250) == 20, "MTU=23 应该切 20，得到 %zu", bleNotifyChunk(23, 250));
  CHECK(bleNotifyChunk(185, 250) == 182, "MTU=185 应该切 182，得到 %zu", bleNotifyChunk(185, 250));
  CHECK(bleNotifyChunk(247, 10) == 10, "剩余比 chunk 小就发剩余，得到 %zu", bleNotifyChunk(247, 10));
  CHECK(bleNotifyChunk(0, 10) == 10, "MTU 未知(0)时退到最小值，且不超过剩余，得到 %zu", bleNotifyChunk(0, 10));
  CHECK(bleNotifyChunk(0, 250) == 20, "MTU 未知(0)时退到 20，得到 %zu", bleNotifyChunk(0, 250));
}

// ---- 一次 bleLinkTick 必须能把一帧吐完 ----
// netTick 是「tick 一次 → 把收到的帧全处理掉」，如果 tick 一次只推一片，
// 一个周期里收到两帧时第二帧的回包就没机会发出去（被静默丢掉）。
static void test_drain_whole_frame() {
  // 245 字节的载荷：MTU=247 时 244+1 要 2 片，MTU=23 时 13 片
  size_t remaining = 245;
  int calls247 = 0;
  while (remaining) { remaining -= bleNotifyChunk(247, remaining); ++calls247; }
  CHECK(calls247 == 2, "MTU=247 时 245 字节应该 2 片，算出来 %d 片", calls247);

  remaining = 245;
  int calls23 = 0;
  while (remaining) { remaining -= bleNotifyChunk(23, remaining); ++calls23; }
  CHECK(calls23 == 13, "MTU=23 时 245 字节应该 13 片，算出来 %d 片", calls23);
}

// ---- 版本字节必须校验 ----
// 帧里第 3 个字节是协议版本。今天两边都是 1，看着"不校验也没事"；
// 哪天改了布局就会变成：新 App 发新布局，旧固件照老布局解析并**执行**命令。
// 坏字节重同步的机制本来就在，多看一眼 ver 的代价只是把这一帧当垃圾丢掉。
static void test_proto_version_guard() {
  uint8_t frame[PROTO_HEADER + PROTO_MAX_PAYLOAD + 2];
  ProtoFrame out;
  ProtoRx rx;

  size_t n = protoBuild(frame, sizeof(frame), CMD_PING, 7, nullptr, 0);
  CHECK(n == 10, "PING 帧应该是 10 字节，得到 %zu", n);

  bool got = false;
  for (size_t i = 0; i < n; i++)
    if (rx.push(frame[i], out)) got = true;
  CHECK(got, "版本正确的帧必须收下");
  CHECK(out.cmd == CMD_PING && out.seq == 7, "收下的帧内容要对");

  // 只有 ver 变、CRC 重算成正确值 —— 除了版本这一关，别的都挑不出毛病
  frame[2] = (uint8_t)(PROTO_VERSION + 1);
  uint16_t crc = protoCrc16(frame + 2, (size_t)PROTO_HEADER - 2);
  frame[n - 2] = (uint8_t)(crc & 0xFF);
  frame[n - 1] = (uint8_t)(crc >> 8);

  rx.reset();
  got = false;
  for (size_t i = 0; i < n; i++)
    if (rx.push(frame[i], out)) got = true;
  CHECK(!got, "版本不对但 CRC 正确的帧，不能吐出来");
}

// ---- 文本模式收帧 ----
// 真机实测：nRF Connect 的写入框默认 UTF-8，手敲的十六进制会以 ASCII 发出来，
// 设备侧按二进制收帧只能静默丢掉（日志里是 "WR n=28: 41 35 20 35 41 ..."）。
// 这里钉住「文本也要能翻成帧」，顺便钉住真正的二进制帧不能误进文本分支。
static void test_proto_from_text() {
  uint8_t buf[PROTO_HEADER + PROTO_MAX_PAYLOAD + 2];
  ProtoFrame f;

  // 各种写法都翻成帧，再喂给**真**收帧器，确认确实是一帧合法的、cmd 对得上的帧
  // seq 单独列：十六进制文本是整帧照抄（seq 在字节里），命令词才是设备自己组帧补 seq
  struct Case { const char *text; uint8_t cmd; size_t payload; uint16_t seq; };
  const Case cases[] = {
      {"A5 5A 01 01 00 00 00 00 E1 E1", CMD_PING, 0, 0},
      {"a5 5a 01 01 00 00 00 00 e1 e1", CMD_PING, 0, 0},
      {"A5 5A 01 01 00 00 00 00 E1E1", CMD_PING, 0, 0},   // 用户实际发过的：末尾漏了空格
      {"0xA5 0x5A 0x01 0x01 0x00 0x00 0x00 0x00 0xE1 0xE1", CMD_PING, 0, 0},
      {"A5 5A 01 03 00 00 00 00 62 A5", CMD_INFO, 0, 0},
      {"PING", CMD_PING, 0, 7},
      {"ping", CMD_PING, 0, 7},
      {"INFO", CMD_INFO, 0, 7},
      {"PAIR", CMD_PAIR_INFO, 0, 7},
      {"CFG", CMD_CFG_GET, 0, 7},
      {"AUTH 280148", CMD_AUTH, 6, 7},
  };
  for (const Case &c : cases) {
    size_t n = protoFromText((const uint8_t *)c.text, std::strlen(c.text), buf, sizeof buf, 7);
    if (n == 0) { CHECK(false, "翻译不出来：\"%s\"", c.text); continue; }
    ProtoRx rx;
    bool got = false;
    for (size_t i = 0; i < n && !got; i++) got = rx.push(buf[i], f);
    CHECK(got, "翻译结果不是一整帧：\"%s\"", c.text);
    if (!got) continue;
    CHECK(f.cmd == c.cmd, "\"%s\" cmd=%02X 期望 %02X", c.text, f.cmd, c.cmd);
    CHECK(f.len == c.payload, "\"%s\" payload=%u 期望 %zu", c.text, f.len, c.payload);
    CHECK(f.seq == c.seq, "\"%s\" seq=%u 期望 %u", c.text, f.seq, c.seq);
    // AUTH 的 6 位数字必须原样留着，不能被当成十六进制吃掉
    if (c.cmd == CMD_AUTH)
      CHECK(std::memcmp(f.payload, "280148", 6) == 0, "AUTH 载荷不对");
  }

  // 认不出来一律返回 0：调用方要按原字节走正常收帧器，别把垃圾当帧
  const char *bads[] = {"", "   ", "PINGO", "PING PONG", "A5 5", "AUTH 28014",
                        "AUTH 2801489", "AUTH abcdef", "HELLO", "ZZ"};
  for (const char *b : bads)
    CHECK(protoFromText((const uint8_t *)b, std::strlen(b), buf, sizeof buf, 0) == 0,
          "不该认出：\"%s\"", b);

  // 二进制帧以 0xA5 开头，不能被文本分支截胡
  uint8_t bin[PROTO_HEADER + 2];
  size_t bn = protoBuild(bin, sizeof bin, CMD_PING, 0, nullptr, 0);
  CHECK(protoFromText(bin, bn, buf, sizeof buf, 0) == 0, "二进制帧被文本分支吃了");
}

// ---- BLE 日志环形队列 ----
// 这块坏了的症状很隐蔽：队列写坏 → App 看到的日志错行/重复 → 排错方向全歪。
// 所以顺序、绕圈、丢最旧、seq 索引这几条都要钉住。
static void test_log_queue() {
  static char storage[4 * LogQueue::LOG_LINE_MAX];   // 4 行，方便压满
  LogQueue q;
  q.attach(storage, 4);
  CHECK(q.ready(), "attach 后应该 ready");
  CHECK(q.size() == 0 && q.total() == 0, "空队列 size/total 应为 0");

  char out[LogQueue::LOG_LINE_MAX];

  // 基本先进先出
  q.push("a");
  q.push("b");
  CHECK(q.size() == 2, "size 应为 2，得到 %d", q.size());
  CHECK(q.peek(out) && !std::strcmp(out, "a"), "peek 应看队首 a，得到 %s", out);
  CHECK(q.peek(out) && !std::strcmp(out, "a"), "peek 不该删元素");
  CHECK(q.pop(out) && !std::strcmp(out, "a"), "第一次 pop 应是 a");
  CHECK(q.pop(out) && !std::strcmp(out, "b"), "第二次 pop 应是 b");
  CHECK(!q.pop(out), "空队列 pop 应返回 false");

  // 绕圈：push 满 → 全读出来，顺序不能乱
  for (int i = 0; i < 4; i++) q.push(std::to_string(i).c_str());
  for (int i = 0; i < 4; i++) {
    CHECK(q.pop(out) && out[0] == (char)('0' + i), "绕圈后第 %d 行应是 %d，得到 %s", i, i, out);
  }
  CHECK(q.size() == 0, "读空后 size 应为 0");

  // 满了丢最旧，并且计数（用干净的队列，seq 才好对账）
  static char storage3[4 * LogQueue::LOG_LINE_MAX];
  LogQueue full;
  full.attach(storage3, 4);
  full.push("1");
  full.push("2");
  full.push("3");
  full.push("4");
  CHECK(full.dropped() == 0 && full.headSeq() == 0, "没满之前不该丢行，headSeq 应为 0");
  full.push("5");                    // 挤掉 "1"
  CHECK(full.size() == 4, "满队列 size 应保持容量 4，得到 %d", full.size());
  CHECK(full.dropped() == 1, "应该记录丢了 1 行，得到 %u", full.dropped());
  CHECK(full.pop(out) && !std::strcmp(out, "2"), "丢最旧之后队首应是 2，得到 %s", out);
  CHECK(full.headSeq() == 2, "队首 seq 应是 2（第 0、1 行已出队/被挤），得到 %llu",
        (unsigned long long)full.headSeq());
  CHECK(full.total() == 5, "total 应累计 5 行，得到 %llu", (unsigned long long)full.total());

  // 超长行截断到 LOG_LINE_MAX-1 并保证以 '\0' 结尾
  static char storage4[2 * LogQueue::LOG_LINE_MAX];
  LogQueue trunc;
  trunc.attach(storage4, 2);
  std::string longline(LogQueue::LOG_LINE_MAX + 40, 'x');
  trunc.push(longline.c_str());
  CHECK(trunc.pop(out) && std::strlen(out) == (size_t)LogQueue::LOG_LINE_MAX - 1,
        "超长行应截断到 %d 字符，得到 %zu", LogQueue::LOG_LINE_MAX - 1, std::strlen(out));

  // 回放：peekSeq 能按 seq 取到，被挤掉的和未来的都取不到
  static char storage2[2 * LogQueue::LOG_LINE_MAX];
  LogQueue r;
  r.attach(storage2, 2);
  r.push("old0");
  r.push("new1");
  r.push("new2");                    // 挤掉 old0
  CHECK(!r.peekSeq(0, out), "已被挤掉的 seq 不该取到");
  CHECK(r.peekSeq(1, out) && !std::strcmp(out, "new1"), "seq=1 应是 new1，得到 %s", out);
  CHECK(r.peekSeq(2, out) && !std::strcmp(out, "new2"), "seq=2 应是 new2，得到 %s", out);
  CHECK(!r.peekSeq(3, out), "还没写到的 seq 不该取到");
  CHECK(r.peekSeq(1, out) && r.size() == 2, "peekSeq 不该删元素");

  // 回放窗口之外的陈货要能一次性丢掉（只挪下标，不搬数据）
  static char storage5[6 * LogQueue::LOG_LINE_MAX];
  LogQueue w;
  w.attach(storage5, 6);
  for (int i = 0; i < 6; i++) w.push(("L" + std::to_string(i)).c_str());
  int d1 = w.dropBefore(4);
  CHECK(d1 == 4, "应丢掉前 4 行，得到 %d", d1);
  CHECK(w.size() == 2, "丢完应剩 2 行，得到 %d", w.size());
  CHECK(w.headSeq() == 4, "丢完队首 seq 应为 4，得到 %llu", (unsigned long long)w.headSeq());
  CHECK(w.dropBefore(4) == 0, "重复丢同一位置应返回 0");
  CHECK(w.dropBefore(99) == 2, "丢到未来等于清空，应返回 2");
  CHECK(w.size() == 0 && w.total() == 6, "清空后 size=0、total 不变");

  // 没绑内存时一律安静失去功能，不能崩（malloc 失败的退化路径）
  LogQueue dead;
  dead.attach(nullptr, 0);
  dead.push("x");
  CHECK(!dead.ready() && dead.size() == 0 && !dead.pop(out), "没绑存储时应完全空转");
}

// ---- CMD_LOG_SUB 载荷解析 ----
static void test_log_sub_parse() {
  ProtoLogSub sub;
  uint8_t p[3];

  CHECK(!protoParseLogSub(nullptr, 0, sub), "空载荷应拒绝");
  CHECK(!protoParseLogSub(p, 0, sub), "len=0 应拒绝");

  p[0] = 0;
  CHECK(protoParseLogSub(p, 1, sub) && sub.mode == 0, "mode=0 应通过");
  p[0] = 1;
  CHECK(protoParseLogSub(p, 1, sub) && sub.mode == 1 && sub.replay == 14,
        "mode=1 不带行数时回放数应取默认 14，得到 %u", sub.replay);
  p[0] = 2; p[1] = 32;
  CHECK(protoParseLogSub(p, 2, sub) && sub.mode == 2 && sub.replay == 32,
        "mode=2 应带回放行数，得到 %u", sub.replay);
  p[0] = 2; p[1] = 0;
  CHECK(protoParseLogSub(p, 2, sub) && sub.replay == 14, "回放 0 行按默认处理");
  p[0] = 3;
  CHECK(!protoParseLogSub(p, 1, sub), "未知 mode 应拒绝");
  p[0] = 0xFF;
  CHECK(!protoParseLogSub(p, 1, sub), "mode=0xFF 应拒绝");
}

int main() {
  test_nes_path();
  test_ble_chunk();
  test_proto_version_guard();
  test_drain_whole_frame();
  test_proto_from_text();
  test_log_queue();
  test_log_sub_parse();
  if (failures) {
    std::printf("\n%d 处失败\n", failures);
    return 1;
  }
  std::printf("全部通过\n");
  return 0;
}
