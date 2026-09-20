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

int main() {
  test_nes_path();
  test_ble_chunk();
  test_drain_whole_frame();
  if (failures) {
    std::printf("\n%d 处失败\n", failures);
    return 1;
  }
  std::printf("全部通过\n");
  return 0;
}
