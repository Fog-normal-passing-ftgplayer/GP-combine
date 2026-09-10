#pragma once
// GP-Fusion 用户按键布局 — 由 GP-Fusion 配置向导自动生成，请勿手改。
#include "menu.h"

#define USER_LAYOUT 1
#define USER_SHOW_LEVER 0

static const LayoutBtn USER_MOVE[] = {
  {0x00000004, 23, 55, 17, "L", 1, 0},
  {0x00000002, 72, 55, 17, "D", 1, 0},
  {0x00000008, 113, 80, 16, "R", 1, 0},
  {0x00000001, 140, 146, 17, "U", 1, 0},
};

static const LayoutBtn USER_CLUSTER[] = {
  {0x00000004, 158, 65, 17, "B3", 0, 0},
  {0x00000008, 196, 51, 17, "B4", 0, 0},
  {0x00000020, 236, 52, 17, "R1", 0, 0},
  {0x00000010, 275, 56, 17, "L1", 0, 0},
  {0x00000001, 156, 102, 17, "B1", 0, 0},
  {0x00000002, 195, 90, 17, "B2", 0, 0},
  {0x00000080, 233, 91, 17, "R2", 0, 0},
  {0x00000040, 274, 97, 17, "L2", 0, 0},
  {0x00000400, 182, 132, 15, "L3", 0, 0},
  {0x00000800, 104, 129, 15, "R3", 0, 0},
};

#define USER_LEVER_X 81
#define USER_LEVER_Y 84
#define USER_LEVER_RING 29
#define USER_LEVER_KNOB 12
