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
#include "../../esp32_170x320/src/net/esp_cfg.h"
#include "../../esp32_170x320/src/net/log_queue.h"
#include "../../esp32_170x320/src/net/pad_cfg.h"
#include "../../esp32_170x320/src/net/profiles.h"

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

// ---- 17 字节配置镜像 ----
// 这份向量 App 侧（android_app 的 EspConfigTest）用的是同一组数字：
// 两边只要有一边把偏移挪了，两套测试里必有一套红。
static void test_esp_cfg() {
  EspCfgFields f;
  f.inputHistory = 1;   // 输入历史开
  f.layout       = 2;   // WASD
  f.bgOpacity    = 3;   // 70%
  f.backlight    = 55;
  f.flipX        = 1;
  f.flipY        = 0;
  f.invert       = 0;
  f.saverMode    = 4;   // 吐司
  f.saverSecs    = 300;
  f.screenOff    = 1;
  f.wireless     = 0;
  f.theme        = 6;
  f.style        = 2;

  uint8_t buf[ESP_CFG_BYTES];
  espCfgEncode(f, buf);

  const uint8_t want[ESP_CFG_BYTES] = {1, 1, 1, 2, 3, 55, 1, 0, 0, 4,
                                       0x2C, 0x01, 1, 0, 6, 2, 0};
  for (size_t i = 0; i < ESP_CFG_BYTES; i++) {
    CHECK(buf[i] == want[i], "第 %zu 字节 = %u，应为 %u", i, (unsigned)buf[i], (unsigned)want[i]);
  }
  CHECK(want[10] == 0x2C && want[11] == 0x01, "夹具自身有问题：300 的小端应该是 2C 01");

  EspCfgFields back;
  CHECK(espCfgDecode(buf, ESP_CFG_BYTES, back), "自己编出来的镜像必须能解回来");
  CHECK(back.saverSecs == 300, "屏保时间往返丢失：%u", (unsigned)back.saverSecs);
  CHECK(back.theme == 6 && back.style == 2, "主题/风格往返错位");
  CHECK(back.inputHistory == 1 && back.layout == 2, "输入历史/按键布局往返错位");
  CHECK(back.backlight == 55, "背光往返错位：%u", (unsigned)back.backlight);

  // 越界值必须被钳到范围里，不能原样落进选项数组（那会让菜单显示乱码）
  EspCfgFields wild;
  wild.inputHistory = 9;
  wild.layout       = 200;
  wild.bgOpacity    = 99;
  wild.backlight    = 250;
  wild.flipX        = 7;
  wild.saverMode    = 42;
  wild.saverSecs    = 60000;
  wild.theme        = 250;
  wild.style        = 9;
  espCfgEncode(wild, buf);
  CHECK(buf[2] == 1, "输入历史该钳到 1，实际 %u", (unsigned)buf[2]);
  CHECK(buf[3] == 3, "按键布局该钳到 3，实际 %u", (unsigned)buf[3]);
  CHECK(buf[4] == 4, "透明度该钳到 4，实际 %u", (unsigned)buf[4]);
  CHECK(buf[5] == 100, "背光该钳到 100，实际 %u", (unsigned)buf[5]);
  CHECK(buf[9] == 6, "屏保模式该钳到 6，实际 %u", (unsigned)buf[9]);
  CHECK((buf[10] | ((uint16_t)buf[11] << 8)) == 600, "屏保时间该钳到 600");
  CHECK(buf[14] == ESP_CFG_THEME_MAX, "主题该钳到上限 %u，实际 %u",
        (unsigned)ESP_CFG_THEME_MAX, (unsigned)buf[14]);
  CHECK(buf[15] == 2, "风格该钳到 2，实际 %u", (unsigned)buf[15]);
  CHECK(buf[0] == ESP_CFG_MAGIC && buf[1] == ESP_CFG_FORMAT, "magic/format 被钳坏了");
  CHECK(buf[16] == 0, "保留字节必须是 0");

  // 长度不够 / 版本不对 → 明确返回 false（调用方据此走"用当前设置重建镜像"）
  CHECK(!espCfgDecode(want, ESP_CFG_BYTES - 1, back), "短一字节必须拒绝");
  uint8_t oldFmt[ESP_CFG_BYTES];
  memcpy(oldFmt, want, ESP_CFG_BYTES);
  oldFmt[1] = 99;
  CHECK(!espCfgDecode(oldFmt, ESP_CFG_BYTES, back), "格式版本不对必须拒绝");
  uint8_t badMagic[ESP_CFG_BYTES];
  memcpy(badMagic, want, ESP_CFG_BYTES);
  badMagic[0] = 0;
  CHECK(!espCfgDecode(badMagic, ESP_CFG_BYTES, back), "magic 不对必须拒绝");
}

// ---- 手柄 / 灯光透传载荷 ----
// App 侧 PadConfigTest 用的是同一组数字：偏移挪一格必有一套红。
static void test_pad_cfg() {
  PadCfgFields g;
  g.inputMode = 2;      // PS3
  g.socdMode  = 3;      // 1ST
  g.dpadMode  = 1;      // LAN
  g.fourWay   = 1;
  g.invertX   = 0;
  g.invertY   = 1;
  g.debounce  = 7;

  uint8_t buf[PAD_CFG_BYTES];
  padCfgEncode(g, buf);
  const uint8_t want[PAD_CFG_BYTES] = {2, 3, 1, 0x05, 7};
  for (size_t i = 0; i < PAD_CFG_BYTES; i++)
    CHECK(buf[i] == want[i], "手柄第 %zu 字节 = %u，应为 %u", i, (unsigned)buf[i], (unsigned)want[i]);

  PadCfgFields back;
  CHECK(padCfgDecode(buf, PAD_CFG_BYTES, back), "自己编出来的手柄载荷必须能解回来");
  CHECK(back.inputMode == 2 && back.socdMode == 3 && back.dpadMode == 1, "手柄枚举往返错位");
  CHECK(back.fourWay == 1 && back.invertX == 0 && back.invertY == 1, "手柄标志位往返错位");
  CHECK(back.debounce == 7, "去抖往返错位：%u", (unsigned)back.debounce);

  // 越界必须钳住：原样落进 gpOpts 会让设备菜单显示乱码，Pico 那边还会收到非法枚举
  PadCfgFields wild;
  wild.inputMode = 200;
  wild.socdMode  = 9;
  wild.dpadMode  = 7;
  wild.fourWay   = 3;
  wild.invertX   = 2;
  wild.invertY   = 5;
  wild.debounce  = 0;      // 去抖 0 等于没去抖，下限是 1
  padCfgEncode(wild, buf);
  CHECK(buf[0] == PAD_INPUT_MAX, "输入模式该钳到 %u，实际 %u", (unsigned)PAD_INPUT_MAX, (unsigned)buf[0]);
  CHECK(buf[1] == 4, "SOCD 该钳到 4，实际 %u", (unsigned)buf[1]);
  CHECK(buf[2] == 2, "D-Pad 该钳到 2，实际 %u", (unsigned)buf[2]);
  CHECK(buf[3] == 0x07, "标志位该按位钳成 1，实际 0x%02X", (unsigned)buf[3]);
  CHECK(buf[4] == 1, "去抖该钳到下限 1，实际 %u", (unsigned)buf[4]);

  CHECK(!padCfgDecode(want, PAD_CFG_BYTES - 1, back), "短一字节的手柄载荷必须拒绝");

  LedCfgFields l;
  l.animation    = 4;   // 自定义
  l.brightness   = 5;
  l.staticColor  = 12;  // MAG
  l.turnOffSuspended = 1;
  l.chaseSpeed   = 92;
  l.rainbowSpeed = 96;
  l.flowSpeed    = 100;

  uint8_t lbuf[LED_CFG_BYTES];
  ledCfgEncode(l, lbuf);
  const uint8_t lwant[LED_CFG_BYTES] = {4, 5, 12, 1, 92, 96, 100};
  for (size_t i = 0; i < LED_CFG_BYTES; i++)
    CHECK(lbuf[i] == lwant[i], "灯光第 %zu 字节 = %u，应为 %u", i, (unsigned)lbuf[i], (unsigned)lwant[i]);

  LedCfgFields lback;
  CHECK(ledCfgDecode(lbuf, LED_CFG_BYTES, lback), "自己编出来的灯光载荷必须能解回来");
  CHECK(lback.animation == 4 && lback.brightness == 5 && lback.staticColor == 12, "灯光枚举往返错位");
  CHECK(lback.turnOffSuspended == 1, "挂起关灯往返错位");
  CHECK(lback.chaseSpeed == 92 && lback.rainbowSpeed == 96 && lback.flowSpeed == 100, "速度往返错位");

  LedCfgFields lwild;
  lwild.animation = 99;
  lwild.brightness = 250;
  lwild.staticColor = 200;
  lwild.turnOffSuspended = 0xFF;
  lwild.chaseSpeed = 250;
  lwild.rainbowSpeed = 0;
  lwild.flowSpeed = 101;
  ledCfgEncode(lwild, lbuf);
  CHECK(lbuf[0] == 5, "动画模式该钳到 5，实际 %u", (unsigned)lbuf[0]);
  CHECK(lbuf[1] == 5, "亮度该钳到 5，实际 %u", (unsigned)lbuf[1]);
  CHECK(lbuf[2] == 15, "静态颜色该钳到 15，实际 %u", (unsigned)lbuf[2]);
  CHECK(lbuf[3] == 0x01, "挂起关灯只该留 bit0，实际 0x%02X", (unsigned)lbuf[3]);
  CHECK(lbuf[4] == 100 && lbuf[6] == 100, "速度该钳到 100，实际 %u/%u", (unsigned)lbuf[4], (unsigned)lbuf[6]);
  CHECK(lbuf[5] == 0, "速度下限是 0，实际 %u", (unsigned)lbuf[5]);
  CHECK(!ledCfgDecode(lwant, LED_CFG_BYTES - 1, lback), "短一字节的灯光载荷必须拒绝");

  // 速度 ↔ 周期时间：换算只在 pad_cfg.h 里有一份，.ino 收发都调它。
  // 表错了的后果是「App 上写 92%，设备实际跑的是另一档」。
  CHECK(ledSpeedToCycle(100) == 1, "100%% 该换算成 cycle=1，实际 %u", (unsigned)ledSpeedToCycle(100));
  CHECK(ledSpeedToCycle(92) == 81, "92%% 该换算成 cycle=81，实际 %u", (unsigned)ledSpeedToCycle(92));
  CHECK(ledSpeedToCycle(0) == 1001, "0%% 该换算成 cycle=1001，实际 %u", (unsigned)ledSpeedToCycle(0));
  CHECK(ledCycleToSpeed(1) == 100, "cycle=1 该换算成 100%%，实际 %u", (unsigned)ledCycleToSpeed(1));
  CHECK(ledCycleToSpeed(81) == 92, "cycle=81 该换算成 92%%，实际 %u", (unsigned)ledCycleToSpeed(81));
  CHECK(ledCycleToSpeed(1001) == 0, "cycle=1001 该换算成 0%%，实际 %u", (unsigned)ledCycleToSpeed(1001));
  // Pico 可能回 0（没配置过）——不能让菜单显示成 101%
  CHECK(ledCycleToSpeed(0) == 100, "cycle=0 该当速度上限，实际 %u", (unsigned)ledCycleToSpeed(0));
  for (int s = 0; s <= 100; s++)
    CHECK(ledCycleToSpeed(ledSpeedToCycle((uint8_t)s)) == s,
          "速度 %d 往返对不上：回来是 %u", s, (unsigned)ledCycleToSpeed(ledSpeedToCycle((uint8_t)s)));
}

// ---- 配置档（/profiles/N.cfg） ----
static void test_profiles() {
  char path[24];
  CHECK(profSlotPath(path, sizeof(path), 1), "档位 1 该有路径");
  CHECK(!strcmp(path, "/profiles/1.cfg"), "档 1 路径是 %s", path);
  CHECK(profSlotPath(path, sizeof(path), 5), "档位 5 该有路径");
  CHECK(!strcmp(path, "/profiles/5.cfg"), "档 5 路径是 %s", path);
  CHECK(!profSlotPath(path, sizeof(path), 0), "档位 0 非法，必须拒绝");
  CHECK(!profSlotPath(path, sizeof(path), 6), "档位 6 非法，必须拒绝");
  // 缓冲不够要拒绝而不是截断：截成 "/pro" 会写进一个不存在的目录，
  // 现象是「保存了但读不回来」
  CHECK(!profSlotPath(path, 4, 1), "缓冲不够必须拒绝");

  // 名字清洗：控制字符（含换行）会破坏配置文件行结构，必须去掉；超长截断
  char name[PROF_NAME_MAX + 1];
  size_t n = profSanitizeName("  街机档\n", name, sizeof(name));
  CHECK(!strcmp(name, "街机档"), "名字该去掉空白，实际 `%s`", name);
  CHECK(n == strlen(name), "返回长度 %zu 与字符串 %zu 不符", n, strlen(name));
  n = profSanitizeName("", name, sizeof(name));
  CHECK(n == 0 && name[0] == 0, "空名字该是空串");
  n = profSanitizeName("abcdefghijklmnopqrstuvwxyz", name, sizeof(name));
  CHECK(n == PROF_NAME_MAX, "超长名字该截到 %zu，实际 %zu", (size_t)PROF_NAME_MAX, n);
  n = profSanitizeName("abcd", name, 4);   // 只能放 3 个字符 + '\0'
  CHECK(n == 3 && !strcmp(name, "abc"), "小缓冲该截到 3，实际 %zu `%s`", n, name);

  // 容器：名字 + 17 字节设置镜像，自带魔数与格式版本
  uint8_t img[ESP_CFG_BYTES];
  EspCfgFields f;
  f.inputHistory = 1; f.layout = 3; f.bgOpacity = 2; f.backlight = 40;
  f.flipX = 0; f.flipY = 1; f.invert = 1; f.saverMode = 5; f.saverSecs = 120;
  f.screenOff = 0; f.wireless = 1; f.theme = 3; f.style = 1;
  espCfgEncode(f, img);

  uint8_t file[PROF_FILE_BYTES];
  CHECK(profEncodeFile(file, sizeof(file), 2, "街机档", img), "编码该成功");
  CHECK(file[0] == 'G' && file[1] == 'P' && file[2] == 'F', "魔数不对");
  CHECK(file[3] == PROF_FILE_FORMAT, "格式版本不对：%u", (unsigned)file[3]);

  char rname[PROF_NAME_MAX + 1];
  uint8_t rimg[ESP_CFG_BYTES];
  uint8_t rslot = 0;
  CHECK(profDecodeFile(file, sizeof(file), &rslot, rname, sizeof(rname), rimg), "解码该成功");
  CHECK(rslot == 2, "档位往返错位：%u", (unsigned)rslot);
  CHECK(!strcmp(rname, "街机档"), "名字往返错位：`%s`", rname);
  for (size_t i = 0; i < ESP_CFG_BYTES; i++)
    CHECK(rimg[i] == img[i], "镜像第 %zu 字节往返错位", i);
  EspCfgFields f2;
  CHECK(espCfgDecode(rimg, ESP_CFG_BYTES, f2) && f2.backlight == 40 && f2.saverSecs == 120,
        "存回来的镜像解不出原值");

  // 坏文件整份拒绝，不能「解一半」把用户设置写花
  uint8_t bad[PROF_FILE_BYTES];
  memcpy(bad, file, sizeof(bad));
  bad[3] = 99;
  CHECK(!profDecodeFile(bad, sizeof(bad), &rslot, rname, sizeof(rname), rimg), "格式版本不对该拒绝");
  CHECK(!profDecodeFile(file, PROF_FILE_BYTES - 1, &rslot, rname, sizeof(rname), rimg), "短一字节该拒绝");
  CHECK(!profEncodeFile(file, PROF_FILE_BYTES - 1, 1, "x", img), "缓冲不够该拒绝");

  // 列表记录：定长，App 侧不用做变长解析
  uint8_t recs[PROF_SLOTS * PROF_RECORD_BYTES];
  memset(recs, 0, sizeof(recs));
  // 固件永远吐满 5 条（没占用的也带上槽号），App 侧直接按下标取
  for (uint8_t i = 1; i <= PROF_SLOTS; i++)
    profEncodeRecord(&recs[(i - 1) * PROF_RECORD_BYTES], i, false, "", 0);
  profEncodeRecord(&recs[0 * PROF_RECORD_BYTES], 1, true, "街机档", (uint8_t)strlen("街机档"));
  profEncodeRecord(&recs[2 * PROF_RECORD_BYTES], 3, true, "", 0);
  uint8_t outSlot = 0, outLen = 0;
  bool outUsed = false;
  char outName[PROF_NAME_MAX + 1];
  profDecodeRecord(&recs[0], outSlot, outUsed, outName, sizeof(outName), outLen);
  CHECK(outSlot == 1 && outUsed && outLen == (uint8_t)strlen("街机档"), "记录 1 的档位/占用/长度不对");
  CHECK(!strcmp(outName, "街机档"), "记录 1 的名字不对：`%s`", outName);
  profDecodeRecord(&recs[1 * PROF_RECORD_BYTES], outSlot, outUsed, outName, sizeof(outName), outLen);
  CHECK(outSlot == 2 && !outUsed && outLen == 0, "空档必须报未占用");
  profDecodeRecord(&recs[2 * PROF_RECORD_BYTES], outSlot, outUsed, outName, sizeof(outName), outLen);
  CHECK(outSlot == 3 && outUsed && outLen == 0, "空名字的档也是已占用");
}

// ---- 蓝牙设置载荷（CMD_BT_SET） ----
static void test_proto_bt_set() {
  uint8_t p[64];
  p[0] = PROTO_BT_SET_NAME | PROTO_BT_SET_PAIR | PROTO_BT_SET_SW;
  p[1] = 1;
  p[2] = 12;                              // "GP-Combine-7"
  memcpy(p + 3, "GP-Combine-7", 12);
  size_t n = 3 + 12;
  p[n++] = 6;
  memcpy(p + n, "280148", 6);
  n += 6;

  ProtoBtSet s;
  CHECK(protoParseBtSet(p, (uint16_t)n, s), "正规载荷该被接受");
  CHECK(s.flags == 0x07 && s.sw == 1, "flags/开关解析错");
  CHECK(s.nameLen == 12 && !strcmp(s.name, "GP-Combine-7"), "名字解析错：`%s`", s.name);
  CHECK(s.pairLen == 6 && !strcmp(s.pair, "280148"), "配对码解析错：`%s`", s.pair);

  // 只切开关：名字/配对码段都是空的，也得能解
  uint8_t q[4] = {PROTO_BT_SET_SW, 1, 0, 0};
  CHECK(protoParseBtSet(q, 4, s), "只切蓝牙开关该被接受");
  CHECK(s.nameLen == 0 && s.pairLen == 0, "只切开关时不该带出名字/配对码");

  // 只改名字：不带配对码段（长度 0）也合法
  uint8_t r[16] = {PROTO_BT_SET_NAME, 0, 3};
  memcpy(r + 3, "ABC", 3);
  r[6] = 0;
  CHECK(protoParseBtSet(r, 7, s), "只改名字该被接受");
  CHECK(!strcmp(s.name, "ABC") && s.pairLen == 0, "只改名字解析错：`%s`", s.name);

  // 非法载荷：一律拒绝，不能"猜用户想说什么"
  uint8_t bad1[4] = {0, 0, 0, 0};
  CHECK(!protoParseBtSet(bad1, 4, s), "flags=0（什么都没改）该拒绝");
  uint8_t bad2[64];
  memcpy(bad2, p, n);
  bad2[2] = 21;
  CHECK(!protoParseBtSet(bad2, (uint16_t)n, s), "名字超 20 字节该拒绝");
  uint8_t bad3[64];
  memcpy(bad3, p, n);
  bad3[3 + 12 + 1 + 2] = 'x';
  CHECK(!protoParseBtSet(bad3, (uint16_t)n, s), "配对码里混进非数字该拒绝");
  uint8_t bad4[64];
  memcpy(bad4, p, n);
  bad4[3 + 12] = 5;
  CHECK(!protoParseBtSet(bad4, (uint16_t)n, s), "配对码长度不是 6 该拒绝");
  CHECK(!protoParseBtSet(p, (uint16_t)(n - 1), s), "长度截断该拒绝");
  uint8_t bad5[4] = {0x80, 1, 0, 0};
  CHECK(!protoParseBtSet(bad5, 4, s), "未知 flag 该拒绝");
  CHECK(!protoParseBtSet(p, 2, s), "少于 3 字节该拒绝");
  uint8_t bad6[8] = {PROTO_BT_SET_NAME, 0, 0, 0};
  CHECK(!protoParseBtSet(bad6, 4, s), "说要改名字却给 0 长度该拒绝");
}

// ---- 配置档保存载荷（CMD_PROF_SAVE） ----
static void test_proto_prof_save() {
  uint8_t p[32];
  p[0] = 3;
  p[1] = 6;
  memcpy(p + 2, "街机", 6);
  ProtoProfSave s;
  CHECK(protoParseProfSave(p, 8, s), "正规载荷该被接受");
  CHECK(s.slot == 3 && s.nameLen == 6 && !strcmp(s.name, "街机"), "档位/名字解析错");

  uint8_t q[2] = {1, 0};
  CHECK(protoParseProfSave(q, 2, s), "空名字（用设备默认名）该被接受");
  CHECK(s.slot == 1 && s.nameLen == 0, "空名字时档位/长度错");

  uint8_t bad[32];
  memcpy(bad, p, 8);
  bad[1] = 21;
  CHECK(!protoParseProfSave(bad, 8, s), "名字超 20 字节该拒绝");
  CHECK(!protoParseProfSave(p, 7, s), "长度不够该拒绝");
  CHECK(!protoParseProfSave(p, 1, s), "少于 2 字节该拒绝");
}

int main() {
  test_nes_path();
  test_ble_chunk();
  test_proto_version_guard();
  test_drain_whole_frame();
  test_proto_from_text();
  test_log_queue();
  test_log_sub_parse();
  test_esp_cfg();
  test_pad_cfg();
  test_profiles();
  test_proto_bt_set();
  test_proto_prof_save();
  if (failures) {
    std::printf("\n%d 处失败\n", failures);
    return 1;
  }
  std::printf("全部通过\n");
  return 0;
}
