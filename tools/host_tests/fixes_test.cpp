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

int main() {
  test_nes_path();
  test_ble_chunk();
  test_proto_version_guard();
  test_drain_whole_frame();
  test_proto_from_text();
  if (failures) {
    std::printf("\n%d 处失败\n", failures);
    return 1;
  }
  std::printf("全部通过\n");
  return 0;
}
