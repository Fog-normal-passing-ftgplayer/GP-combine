#pragma once
// GP-Fusion 用户按键布局 — 由 GP-Fusion 配置向导自动生成，请勿手改。
#include "menu.h"

#define USER_LAYOUT 1
#define USER_SHOW_LEVER 0

static const LayoutBtn USER_MOVE[] = {
  {0x00000004, 23, 55, 17, "L", 1, 0},
  {0x00000002, 72, 55, 17, "D", 1, 0},
  {0x00000008, 113, 80, 16, "R", 1, 0},
  {0x00000001, 134, 144, 17, "U", 1, 0},
};

static const LayoutBtn USER_CLUSTER[] = {
  {0x00000004, 155, 61, 17, "B3", 0, 0},
  {0x00000008, 197, 45, 16, "B4", 0, 0},
  {0x00000020, 243, 45, 16, "R1", 0, 0},
  {0x00000010, 285, 49, 17, "L1", 0, 0},
  {0x00000001, 150, 104, 18, "B1", 0, 0},
  {0x00000002, 195, 89, 16, "B2", 0, 0},
  {0x00000080, 239, 88, 16, "R2", 0, 0},
  {0x00000040, 280, 95, 15, "L2", 0, 0},
  {0x00000400, 181, 132, 13, "L3", 0, 1},
  {0x00000800, 96, 128, 13, "R3", 0, 1},
};

#define USER_LEVER_X 51
#define USER_LEVER_Y 101
#define USER_LEVER_RING 22
#define USER_LEVER_KNOB 7
