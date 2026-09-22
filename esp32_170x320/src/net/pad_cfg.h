#pragma once
// 手柄 / 灯光设置的透传载荷编解码（纯函数，无 Arduino 依赖）。
//
// 为什么单独一份：这三个消费者要对齐——ESP 固件、App 的 Kotlin 侧、主机测试。
// 单位刻意用**设备菜单的单位**（枚举索引、百分比），不是发给 Pico 那两帧的原始字节：
//   * 菜单里显示 92% 的追逐速度，App 上写 92 就是 92，中间不再多一次换算
//   * 周期时间 ↔ 百分比的换算只在 [ledSpeedToCycle]/[ledCycleToSpeed] 里有一份
//
// 载荷布局（**改这里必须同步改 android_app/.../proto/PadConfig.kt 和它的测试向量**）：
//
//   手柄（PAD_CFG_BYTES = 5）—— 就是发给 Pico 的 0x04 CONFIG 帧载荷
//     0  输入模式   0..PAD_INPUT_MAX（17 种）
//     1  SOCD      0..4
//     2  D-Pad     0..2
//     3  标志位     bit0 四向 / bit1 反向X / bit2 反向Y
//     4  去抖延迟  1..20 (ms)
//
//   灯光（LED_CFG_BYTES = 7）—— 原始帧里是周期时间 u16，这里换成菜单的百分比
//     0  动画模式  0..5
//     1  亮度      0..5
//     2  静态颜色  0..15
//     3  标志位    bit0 挂起关灯
//     4  追逐速度  0..100
//     5  彩虹速度  0..100
//     6  流水速度  0..100

#include <stddef.h>
#include <stdint.h>

static const size_t  PAD_CFG_BYTES = 5;
static const size_t  LED_CFG_BYTES = 7;
static const uint8_t PAD_INPUT_MAX = 16;   // INPUT_NAMES 有 17 项，索引 0..16
static const uint8_t PAD_SOCD_MAX  = 4;
static const uint8_t PAD_DPAD_MAX  = 2;
static const uint8_t PAD_DEBOUNCE_MIN = 1;
static const uint8_t PAD_DEBOUNCE_MAX = 20;
static const uint8_t LED_ANIM_MAX  = 5;
static const uint8_t LED_BRIGHT_MAX = 5;
static const uint8_t LED_COLOR_MAX = 15;
static const uint8_t LED_SPEED_MAX = 100;

struct PadCfgFields {
  uint8_t inputMode;
  uint8_t socdMode;
  uint8_t dpadMode;
  uint8_t fourWay;
  uint8_t invertX;
  uint8_t invertY;
  uint8_t debounce;
};

struct LedCfgFields {
  uint8_t animation;
  uint8_t brightness;
  uint8_t staticColor;
  uint8_t turnOffSuspended;
  uint8_t chaseSpeed;
  uint8_t rainbowSpeed;
  uint8_t flowSpeed;
};

static inline uint8_t padClampU8(int v, int lo, int hi) {
  if (v < lo) return (uint8_t)lo;
  if (v > hi) return (uint8_t)hi;
  return (uint8_t)v;
}

// 速度(0..100) → Pico 的周期时间(1..1001)。和设备菜单原来那两行 inline 公式一致：
// 菜单值越大 = 周期越短 = 跑得越快。
static inline uint16_t ledSpeedToCycle(uint8_t speed) {
  uint8_t s = padClampU8(speed, 0, LED_SPEED_MAX);
  return (uint16_t)((100 - (int)s) * 10 + 1);
}

// 周期时间 → 速度。Pico 那边可能是 0（老配置/没配过），当速度上限处理，
// 不能算成 101% —— 菜单会显示越界的选项名。
static inline uint8_t ledCycleToSpeed(uint16_t cycle) {
  if (cycle == 0) return LED_SPEED_MAX;
  int s = 100 - ((int)cycle - 1) / 10;
  return padClampU8(s, 0, LED_SPEED_MAX);
}

static inline void padCfgClamp(PadCfgFields &f) {
  f.inputMode = padClampU8(f.inputMode, 0, PAD_INPUT_MAX);
  f.socdMode  = padClampU8(f.socdMode, 0, PAD_SOCD_MAX);
  f.dpadMode  = padClampU8(f.dpadMode, 0, PAD_DPAD_MAX);
  f.fourWay   = f.fourWay ? 1 : 0;
  f.invertX   = f.invertX ? 1 : 0;
  f.invertY   = f.invertY ? 1 : 0;
  f.debounce  = padClampU8(f.debounce, PAD_DEBOUNCE_MIN, PAD_DEBOUNCE_MAX);
}

static inline void ledCfgClamp(LedCfgFields &f) {
  f.animation    = padClampU8(f.animation, 0, LED_ANIM_MAX);
  f.brightness   = padClampU8(f.brightness, 0, LED_BRIGHT_MAX);
  f.staticColor  = padClampU8(f.staticColor, 0, LED_COLOR_MAX);
  f.turnOffSuspended = f.turnOffSuspended ? 1 : 0;
  f.chaseSpeed   = padClampU8(f.chaseSpeed, 0, LED_SPEED_MAX);
  f.rainbowSpeed = padClampU8(f.rainbowSpeed, 0, LED_SPEED_MAX);
  f.flowSpeed    = padClampU8(f.flowSpeed, 0, LED_SPEED_MAX);
}

static inline void padCfgEncode(const PadCfgFields &f, uint8_t *out) {
  PadCfgFields c = f;
  padCfgClamp(c);
  out[0] = c.inputMode;
  out[1] = c.socdMode;
  out[2] = c.dpadMode;
  out[3] = (uint8_t)((c.fourWay ? 0x01 : 0) | (c.invertX ? 0x02 : 0) | (c.invertY ? 0x04 : 0));
  out[4] = c.debounce;
}

// 长度对不上返回 false（调用方回 ERR_BAD_LEN）。顺手把每个字段钳到范围里 ——
// 越界值落进 gpOpts 会让设备菜单显示乱码，还会把非法枚举发给 Pico。
static inline bool padCfgDecode(const uint8_t *in, size_t len, PadCfgFields &f) {
  if (in == nullptr || len < PAD_CFG_BYTES) return false;
  f.inputMode = in[0];
  f.socdMode  = in[1];
  f.dpadMode  = in[2];
  f.fourWay   = (in[3] & 0x01) ? 1 : 0;
  f.invertX   = (in[3] & 0x02) ? 1 : 0;
  f.invertY   = (in[3] & 0x04) ? 1 : 0;
  f.debounce  = in[4];
  padCfgClamp(f);
  return true;
}

static inline void ledCfgEncode(const LedCfgFields &f, uint8_t *out) {
  LedCfgFields c = f;
  ledCfgClamp(c);
  out[0] = c.animation;
  out[1] = c.brightness;
  out[2] = c.staticColor;
  out[3] = (uint8_t)(c.turnOffSuspended ? 0x01 : 0);
  out[4] = c.chaseSpeed;
  out[5] = c.rainbowSpeed;
  out[6] = c.flowSpeed;
}

static inline bool ledCfgDecode(const uint8_t *in, size_t len, LedCfgFields &f) {
  if (in == nullptr || len < LED_CFG_BYTES) return false;
  f.animation    = in[0];
  f.brightness   = in[1];
  f.staticColor  = in[2];
  f.turnOffSuspended = (in[3] & 0x01) ? 1 : 0;
  f.chaseSpeed   = in[4];
  f.rainbowSpeed = in[5];
  f.flowSpeed    = in[6];
  ledCfgClamp(f);
  return true;
}
