// InfoNES -> ESP32-S3 系统层（GP-Combine 170x320）
// ROM 从 LittleFS 读入 PSRAM；画面写入固件 lfb（320x170）并按缩放模式输出；
// 手柄来自 UART 快照；无声（pAPU 仍运行但无输出设备）。
//
// InfoNES 核心版权：Copyright (C) 2000 Kiyoka Nishiyama (InfoNES Project)、
// Copyright (C) 2020-2024 jay-kumogata（SDL/Linux 移植），Apache License 2.0
// （完整文本见同目录 LICENSE）。本文件是 GP-Combine 为 ESP32-S3 写的移植层。
#pragma GCC optimize("O2")   // 模拟器热点：默认 -Os 帧率不够
#include <Arduino.h>
#include <LittleFS.h>
#include <esp_heap_caps.h>

#include "InfoNES.h"
#include "InfoNES_System.h"
#include "InfoNES_pAPU.h"

// 固件侧提供
// 注意：固件里的定义是真数组 uint16_t lfb[SCR_W * SCR_H]（320*170），
// 不能声明成指针，否则会把帧缓冲第一个像素当指针用 -> StoreProhibited 崩溃。
extern uint16_t lfb[];                // 320x170 内容帧缓冲
extern volatile uint16_t lastButtons; // B1..A2 位
extern volatile uint8_t  lastDpad;    // U/D/L/R = 0x01/0x02/0x04/0x08
extern void pushFrame();

#define NES_OUT_W 320
#define NES_OUT_H 170

// NES 手柄串行位序：bit0=A bit1=B bit2=Select bit3=Start bit4=Up bit5=Down bit6=Left bit7=Right
#define NES_PAD_A      0x01
#define NES_PAD_B      0x02
#define NES_PAD_SELECT 0x04
#define NES_PAD_START  0x08
#define NES_PAD_UP     0x10
#define NES_PAD_DOWN   0x20
#define NES_PAD_LEFT   0x40
#define NES_PAD_RIGHT  0x80

// 64 色 NES 调色板（RGB565）。源表来自 InfoNES 移植版，但那是 RGB555
// (0RRRRRGGGGGBBBBB, bit15 不用)，直接当 RGB565 用颜色会全错，
// 这里已按 555->565 精确转换（绿色补低位）。
WORD NesPalette[64] =
{
  0x738e, 0x20d1, 0x0015, 0x4013, 0x880e, 0xa802, 0xa000, 0x7840,
  0x4140, 0x0200, 0x0280, 0x01c2, 0x19cb, 0x0000, 0x0000, 0x0000,
  0xbdf7, 0x039d, 0x21dd, 0x801e, 0xb817, 0xe00b, 0xd940, 0xca41,
  0x8b80, 0x04a0, 0x0560, 0x04a7, 0x0431, 0x0000, 0x0000, 0x0000,
  0xffff, 0x3dff, 0x5cbf, 0x447f, 0xf3df, 0xfb96, 0xfb8c, 0xfce7,
  0xf5e7, 0x86a2, 0x4ee9, 0x5ff3, 0x077b, 0x0000, 0x0000, 0x0000,
  0xffff, 0xaf3f, 0xc6bf, 0xd67f, 0xfe3f, 0xfe3b, 0xfdf6, 0xfef5,
  0xff34, 0xe7f4, 0xafb7, 0xb7f9, 0x9ffe, 0x0000, 0x0000, 0x0000,
};

struct ApuEvent_t;
extern ApuEvent_t *ApuEventQueue;   // InfoNES_pAPU.cpp
extern BYTE *DRAM;                  // InfoNES_Mapper.cpp
extern BYTE *wave_buffers_flat;     // InfoNES_pAPU.cpp
#define DRAM_SIZE_ 0xA000

static BYTE *romBuf = nullptr;
static BYTE *vromBuf = nullptr;

// 大缓冲统一放 PSRAM（WorkFrame 120KB / ChrBuf 32KB）
bool EspNesAllocBuffers()
{
  if (WorkFrame == nullptr) {
    WorkFrame = (WORD *)heap_caps_malloc(
        (size_t)NES_DISP_WIDTH * NES_DISP_HEIGHT * sizeof(WORD), MALLOC_CAP_SPIRAM);
  }
  if (ChrBuf == nullptr) {
    ChrBuf = (BYTE *)heap_caps_malloc(256 * 2 * 8 * 8, MALLOC_CAP_SPIRAM);
  }
  if (ApuEventQueue == nullptr) {
    ApuEventQueue = (ApuEvent_t *)heap_caps_malloc(
        sizeof(ApuEvent_t) * APU_EVENT_MAX, MALLOC_CAP_SPIRAM);
  }
  if (DRAM == nullptr) {
    DRAM = (BYTE *)heap_caps_malloc(DRAM_SIZE_, MALLOC_CAP_SPIRAM);
  }
  if (wave_buffers_flat == nullptr) {
    wave_buffers_flat = (BYTE *)heap_caps_malloc(5 * 735, MALLOC_CAP_SPIRAM);
  }

  // 必须显式 return：这个函数声明为 bool，早期版本漏了 return，
  // 编译器在 -Os 下会把函数末尾的 ret 优化掉，于是分配完后直接"贯穿"
  // 执行后面 InfoNES_ReleaseRom / InfoNES_LoadFrame 等函数的函数体，
  // 表现为一按 A 进游戏就卡死。
  return WorkFrame && ChrBuf && ApuEventQueue && DRAM && wave_buffers_flat;
}

int InfoNES_ReadRom(const char *pszFileName)
{
  File fp = LittleFS.open(pszFileName, "r");
  if (!fp) return -1;

  if (fp.read((uint8_t *)&NesHeader, sizeof(NesHeader)) != sizeof(NesHeader)) {
    fp.close(); return -1;
  }
  if (memcmp(NesHeader.byID, "NES\x1a", 4) != 0) {   // 不是 .nes
    fp.close(); return -1;
  }

  memset(SRAM, 0, SRAM_SIZE);
  if (NesHeader.byInfo1 & 4) fp.read(&SRAM[0x1000], 512);   // trainer

  if (romBuf) { heap_caps_free(romBuf); romBuf = nullptr; }
  ROM = romBuf = (BYTE *)heap_caps_malloc((size_t)NesHeader.byRomSize * 0x4000,
                                         MALLOC_CAP_SPIRAM);
  if (ROM == nullptr) { fp.close(); return -1; }
  fp.read(ROM, (size_t)0x4000 * NesHeader.byRomSize);

  if (NesHeader.byVRomSize > 0) {
    if (vromBuf) { heap_caps_free(vromBuf); vromBuf = nullptr; }
    VROM = vromBuf = (BYTE *)heap_caps_malloc((size_t)NesHeader.byVRomSize * 0x2000,
                                             MALLOC_CAP_SPIRAM);
    if (VROM == nullptr) { fp.close(); return -1; }
    fp.read(VROM, (size_t)0x2000 * NesHeader.byVRomSize);
  } else {
    VROM = nullptr;
  }
  fp.close();
  return 0;
}

void InfoNES_ReleaseRom()
{
  if (romBuf) { heap_caps_free(romBuf); romBuf = nullptr; }
  if (vromBuf) { heap_caps_free(vromBuf); vromBuf = nullptr; }
  ROM = nullptr;
  VROM = nullptr;
}

void InfoNES_LoadFrame()
{
  if (WorkFrame == nullptr) return;
  const int sw = NES_DISP_WIDTH;    // 256
  const int sh = NES_DISP_HEIGHT;   // 240
  // 注意：WorkFrame 的 bit15 是 InfoNES 内部标记（"背景色/精灵优先级"），
  // 不是 RGB565 的一部分，必须掩掉，否则整屏偏红。
#if NES_SCALE_MODE == 1
  // 等比居中（左右黑边）：按高度铺满 -> 181x170
  const int dw = sw * NES_OUT_H / sh;
  const int x0 = (NES_OUT_W - dw) / 2;
  for (int y = 0; y < NES_OUT_H; y++) {
    const int sy = y * sh / NES_OUT_H;
    const WORD *src = WorkFrame + sy * sw;
    uint16_t *dst = lfb + y * NES_OUT_W;
    for (int x = 0; x < NES_OUT_W; x++) dst[x] = 0;
    for (int x = 0; x < dw; x++) dst[x0 + x] = src[x * sw / dw] & 0x7FFF;
  }
#else
  // 拉伸铺满全屏
  for (int y = 0; y < NES_OUT_H; y++) {
    const int sy = y * sh / NES_OUT_H;
    const WORD *src = WorkFrame + sy * sw;
    uint16_t *dst = lfb + y * NES_OUT_W;
    for (int x = 0; x < NES_OUT_W; x++) dst[x] = src[x * sw / NES_OUT_W] & 0x7FFF;
  }
#endif
  pushFrame();
}

void InfoNES_PadState(DWORD *pdwPad1, DWORD *pdwPad2, DWORD *pdwSystem)
{
  const uint16_t b = lastButtons;   // B1=0x0001 B2=0x0002 B3=0x0004 B4=0x0008 S1=0x0100 S2=0x0200
  const uint8_t d = lastDpad;
  DWORD pad = 0;
  if (d & 0x01) pad |= NES_PAD_UP;
  if (d & 0x02) pad |= NES_PAD_DOWN;
  if (d & 0x04) pad |= NES_PAD_LEFT;
  if (d & 0x08) pad |= NES_PAD_RIGHT;
  if (b & 0x0001) pad |= NES_PAD_A;
  if (b & 0x0002) pad |= NES_PAD_B;
  if (b & 0x0004) pad |= NES_PAD_START;   // B3
  if (b & 0x0008) pad |= NES_PAD_SELECT;  // B4
  *pdwPad1 = pad;
  *pdwPad2 = 0;
  // S1+S2 长按 1 秒 -> 让 InfoNES_Cycle 返回 -1 退出（由固件判别）
  static DWORD quitHold = 0;
  if ((b & 0x0300) == 0x0300) {
    quitHold++;
    *pdwSystem = (quitHold > 60) ? PAD_SYS_QUIT : 0;
  } else {
    quitHold = 0;
    *pdwSystem = 0;
  }
}

void *InfoNES_MemoryCopy(void *dest, const void *src, int count)
{
  return memcpy(dest, src, (size_t)count);
}

void *InfoNES_MemorySet(void *dest, int c, int count)
{
  return memset(dest, c, (size_t)count);
}

void InfoNES_DebugPrint(char *pszMsg) { (void)pszMsg; }
void InfoNES_MessageBox(char *pszMsg, ...) { (void)pszMsg; }
void InfoNES_Wait() {}
int  InfoNES_Menu() { return 0; }

// ---- 无声：所有声音接口留空（pAPU 仍计算，但无输出设备） ----
void InfoNES_SoundInit(void) {}
int  InfoNES_SoundOpen(int samples_per_sync, int sample_rate) { (void)samples_per_sync; (void)sample_rate; return 0; }
void InfoNES_SoundClose(void) {}
void InfoNES_SoundOutput(int samples, BYTE *wave1, BYTE *wave2, BYTE *wave3, BYTE *wave4, BYTE *wave5)
{ (void)samples; (void)wave1; (void)wave2; (void)wave3; (void)wave4; (void)wave5; }

// 供固件检查：全部缓冲就绪才算成功
bool EspNesBuffersReady()
{
  return WorkFrame && ChrBuf && ApuEventQueue && DRAM && wave_buffers_flat;
}
