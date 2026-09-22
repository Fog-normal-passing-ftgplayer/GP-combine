#pragma once
// 17 字节"ESP 配置镜像"的编解码。
//
// 为什么抽出来：这份布局有三个消费者——ESP 固件、App 的 Kotlin 侧、主机测试。
// 留在 .ino 里的话主机测试够不到（.ino 编不了），两边一漂就是"App 改了设置设备没反应"
// 这种最难查的 bug。所以这里只有纯函数，不含任何 Arduino 依赖。
//
// 字节布局（**改这里必须同步改 android_app/.../proto/EspConfig.kt 和它的测试向量**）：
//   0      magic  = 1
//   1      format = ESP_CFG_FORMAT
//   2      输入历史      0..1
//   3      按键布局      0..3
//   4      背景透明度    0..4
//   5      背光亮度      0..100
//   6      水平翻转      0..1
//   7      垂直翻转      0..1
//   8      反色          0..1
//   9      屏保模式      0..6
//   10..11 屏保时间      0..600（小端 u16）
//   12     关屏          0..1
//   13     无线开关      0..1
//   14     主题          0..ESP_CFG_THEME_MAX
//   15     风格          0..2
//   16     保留（0）

#include <stddef.h>
#include <stdint.h>

static const size_t  ESP_CFG_BYTES     = 17;
static const uint8_t ESP_CFG_MAGIC     = 1;
static const uint8_t ESP_CFG_FORMAT    = 1;
static const uint8_t ESP_CFG_THEME_MAX = 9;    // 主题数 - 1，.ino 里有 static_assert 盯着

struct EspCfgFields {
  uint8_t  inputHistory;   // 输入历史
  uint8_t  layout;         // 按键布局
  uint8_t  bgOpacity;      // 背景透明度
  uint8_t  backlight;      // 背光亮度
  uint8_t  flipX;          // 水平翻转
  uint8_t  flipY;          // 垂直翻转
  uint8_t  invert;         // 反色
  uint8_t  saverMode;      // 屏保模式
  uint16_t saverSecs;      // 屏保时间（秒）
  uint8_t  screenOff;      // 关屏
  uint8_t  wireless;       // 无线开关
  uint8_t  theme;          // 主题
  uint8_t  style;          // 风格
};

static inline uint8_t espCfgClampI(int v, int lo, int hi) {
  if (v < lo) return (uint8_t)lo;
  if (v > hi) return (uint8_t)hi;
  return (uint8_t)v;
}

// 屏保时间是 u16，不能走上面那个返回 u8 的版本（300 会被截成 44——实测踩过）
static inline uint16_t espCfgClampU16(int v, int lo, int hi) {
  if (v < lo) return (uint16_t)lo;
  if (v > hi) return (uint16_t)hi;
  return (uint16_t)v;
}

// 值域钳制到各自范围（跟设备菜单的 OPT_* 上下限一致）
static inline void espCfgClamp(EspCfgFields &f) {
  f.inputHistory = espCfgClampI(f.inputHistory, 0, 1);
  f.layout       = espCfgClampI(f.layout, 0, 3);
  f.bgOpacity    = espCfgClampI(f.bgOpacity, 0, 4);
  f.backlight    = espCfgClampI(f.backlight, 0, 100);
  f.flipX        = espCfgClampI(f.flipX, 0, 1);
  f.flipY        = espCfgClampI(f.flipY, 0, 1);
  f.invert       = espCfgClampI(f.invert, 0, 1);
  f.saverMode    = espCfgClampI(f.saverMode, 0, 6);
  f.saverSecs    = espCfgClampU16(f.saverSecs, 0, 600);
  f.screenOff    = espCfgClampI(f.screenOff, 0, 1);
  f.wireless     = espCfgClampI(f.wireless, 0, 1);
  f.theme        = espCfgClampI(f.theme, 0, ESP_CFG_THEME_MAX);
  f.style        = espCfgClampI(f.style, 0, 2);
}

static inline void espCfgEncode(const EspCfgFields &f, uint8_t *out) {
  EspCfgFields c = f;
  espCfgClamp(c);
  out[0]  = ESP_CFG_MAGIC;
  out[1]  = ESP_CFG_FORMAT;
  out[2]  = c.inputHistory;
  out[3]  = c.layout;
  out[4]  = c.bgOpacity;
  out[5]  = c.backlight;
  out[6]  = c.flipX;
  out[7]  = c.flipY;
  out[8]  = c.invert;
  out[9]  = c.saverMode;
  out[10] = (uint8_t)(c.saverSecs & 0xFF);
  out[11] = (uint8_t)((c.saverSecs >> 8) & 0xFF);
  out[12] = c.screenOff;
  out[13] = c.wireless;
  out[14] = c.theme;
  out[15] = c.style;
  out[16] = 0;
}

// 长度或版本对不上返回 false（调用方决定是"用当前设置重建镜像"还是"忽略这一帧"）
static inline bool espCfgDecode(const uint8_t *in, size_t len, EspCfgFields &f) {
  if (len < ESP_CFG_BYTES) return false;
  if (in[0] != ESP_CFG_MAGIC || in[1] != ESP_CFG_FORMAT) return false;
  f.inputHistory = in[2];
  f.layout       = in[3];
  f.bgOpacity    = in[4];
  f.backlight    = in[5];
  f.flipX        = in[6];
  f.flipY        = in[7];
  f.invert       = in[8];
  f.saverMode    = in[9];
  f.saverSecs    = (uint16_t)(in[10] | ((uint16_t)in[11] << 8));
  f.screenOff    = in[12];
  f.wireless     = in[13];
  f.theme        = in[14];
  f.style        = in[15];
  espCfgClamp(f);
  return true;
}
