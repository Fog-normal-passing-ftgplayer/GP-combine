#pragma once
// 配置档（/profiles/N.cfg）的纯逻辑：路径拼接、名字清洗、容器编解码。
//
// 抽出来的理由和 esp_cfg.h 一样：真代码在 .ino 里测试够不着，而配置文件写坏了
// 的现象是「保存成功、加载回来设置是乱的」——只在板子上试很难定位。
//
// 容器（PROF_FILE_BYTES = 42，定长）：
//   0..2   'G''P''F'
//   3      格式版本 PROF_FILE_FORMAT
//   4      档位 1..PROF_SLOTS
//   5      名字长度 0..PROF_NAME_MAX
//   6..25  名字（定长 PROF_NAME_MAX 字节，不足补 0）
//   26..42 17 字节设置镜像（就是 esp_cfg.h 那份，自带 magic/format）
//
// 列表记录（PROF_RECORD_BYTES = 23，定长，App 侧不用做变长解析）：
//   0  档位 1..PROF_SLOTS
//   1  是否已占用
//   2  名字长度
//   3..22 名字（定长 PROF_NAME_MAX 字节）

#include <stddef.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

static const uint8_t PROF_SLOTS      = 5;
static const size_t  PROF_NAME_MAX   = 20;   // 字节，不是字符：中文 UTF-8 一个字 3 字节
static const size_t  PROF_FILE_BYTES = 42;
static const size_t  PROF_RECORD_BYTES = 23;
static const uint8_t PROF_FILE_FORMAT = 1;
static const size_t  PROF_NAME_OFF   = 6;
static const size_t  PROF_IMAGE_OFF  = 26;

// 路径缓冲至少要这么多（含 '\0'）："/profiles/5.cfg" 是 15 字节
static const size_t PROF_PATH_BYTES = 16;

static inline bool profValidSlot(uint8_t slot) {
  return slot >= 1 && slot <= PROF_SLOTS;
}

// 缓冲不够返回 false 而不是截断：截成 "/pro" 会写进一个不存在的目录，
// 现象是「保存了但读不回来」，比直接报错难查得多。
static inline bool profSlotPath(char *out, size_t cap, uint8_t slot) {
  if (out == nullptr || !profValidSlot(slot)) return false;
  int n = snprintf(out, cap, "/profiles/%u.cfg", (unsigned)slot);
  return n > 0 && (size_t)n < cap;
}

// 去掉首尾空白和控制字符，超长截断。控制字符（尤其换行）会破坏配置文件的
// 行结构；截断按字节做，中文名字最坏会在最后一个字中间切断 —— App 侧限制
// 输入字节数来避免，这里只保证「不会写出坏文件」。
static inline size_t profSanitizeName(const char *in, char *out, size_t cap) {
  if (out == nullptr || cap == 0) return 0;
  out[0] = 0;
  if (in == nullptr) return 0;

  size_t n = strlen(in);
  size_t b = 0, e = n;
  auto isSpace = [](char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; };
  while (b < e && isSpace(in[b])) b++;
  while (e > b && isSpace(in[e - 1])) e--;

  size_t limit = PROF_NAME_MAX;
  if (limit > cap - 1) limit = cap - 1;
  size_t w = 0;
  for (size_t i = b; i < e && w < limit; i++) {
    unsigned char c = (unsigned char)in[i];
    if (c < 0x20 || c == 0x7F) continue;   // 控制字符直接丢
    out[w++] = (char)c;
  }
  out[w] = 0;
  return w;
}

static inline bool profEncodeFile(uint8_t *out, size_t cap, uint8_t slot,
                                  const char *name, const uint8_t *image17) {
  if (out == nullptr || image17 == nullptr || cap < PROF_FILE_BYTES) return false;
  if (!profValidSlot(slot)) return false;
  char clean[PROF_NAME_MAX + 1];
  size_t n = profSanitizeName(name, clean, sizeof(clean));

  memset(out, 0, PROF_FILE_BYTES);
  out[0] = 'G';
  out[1] = 'P';
  out[2] = 'F';
  out[3] = PROF_FILE_FORMAT;
  out[4] = slot;
  out[5] = (uint8_t)n;
  memcpy(out + PROF_NAME_OFF, clean, n);
  memcpy(out + PROF_IMAGE_OFF, image17, 17);
  return true;
}

// 任何一处不对（长度、魔数、格式、档位、名字长度）都整份拒绝：
// "解一半"会把用户设置写花，比明确报错糟糕。
static inline bool profDecodeFile(const uint8_t *in, size_t len, uint8_t *slotOut,
                                  char *nameOut, size_t nameCap, uint8_t *imageOut) {
  if (in == nullptr || len < PROF_FILE_BYTES) return false;
  if (in[0] != 'G' || in[1] != 'P' || in[2] != 'F') return false;
  if (in[3] != PROF_FILE_FORMAT) return false;
  if (!profValidSlot(in[4])) return false;
  uint8_t nameLen = in[5];
  if (nameLen > PROF_NAME_MAX) return false;

  if (slotOut) *slotOut = in[4];
  if (nameOut && nameCap) {
    size_t n = nameLen;
    if (n > nameCap - 1) n = nameCap - 1;
    memcpy(nameOut, in + PROF_NAME_OFF, n);
    nameOut[n] = 0;
  }
  if (imageOut) memcpy(imageOut, in + PROF_IMAGE_OFF, 17);
  return true;
}

static inline void profEncodeRecord(uint8_t *out, uint8_t slot, bool used,
                                    const char *name, uint8_t nameLen) {
  if (out == nullptr) return;
  memset(out, 0, PROF_RECORD_BYTES);
  out[0] = slot;
  out[1] = used ? 1 : 0;
  if (nameLen > PROF_NAME_MAX) nameLen = (uint8_t)PROF_NAME_MAX;
  out[2] = nameLen;
  if (name && nameLen) memcpy(out + 3, name, nameLen);
}

static inline void profDecodeRecord(const uint8_t *in, uint8_t &slot, bool &used,
                                    char *nameOut, size_t nameCap, uint8_t &nameLen) {
  slot = in ? in[0] : 0;
  used = in && in[1] != 0;
  nameLen = in ? in[2] : 0;
  if (nameLen > PROF_NAME_MAX) nameLen = (uint8_t)PROF_NAME_MAX;
  if (nameOut && nameCap) {
    size_t n = nameLen;
    if (n > nameCap - 1) n = nameCap - 1;
    if (in) memcpy(nameOut, in + 3, n);
    nameOut[n] = 0;
  }
}
