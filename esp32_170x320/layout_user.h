#pragma once
// GP-Fusion 用户按键布局 — 由 GP-Fusion 配置向导自动生成，请勿手改。
#include "menu.h"

#define USER_LAYOUT 1
#define USER_SHOW_LEVER 1

static const LayoutBtn USER_MOVE[] = {
  {0x00000004, 23, 55, 17, "L", 1, 0},
  {0x00000002, 72, 55, 17, "D", 1, 0},
  {0x00000008, 113, 80, 16, "R", 1, 0},
  {0x00000001, 140, 146, 17, "U", 1, 0},
};

static const LayoutBtn USER_CLUSTER[] = {
  {0x00000004, 155, 58, 17, "B3", 0, 0},
  {0x00000008, 195, 47, 17, "B4", 0, 0},
  {0x00000020, 235, 48, 17, "R1", 0, 0},
  {0x00000010, 276, 58, 17, "L1", 0, 0},
  {0x00000001, 154, 102, 17, "B1", 0, 0},
  {0x00000002, 194, 91, 17, "B2", 0, 0},
  {0x00000080, 234, 93, 17, "R2", 0, 0},
  {0x00000040, 275, 105, 17, "L2", 0, 0},
  {0x00000400, 163, 20, 15, "L3", 0, 0},
  {0x00000800, 166, 139, 15, "R3", 0, 0},
};

#define USER_LEVER_X 81
#define USER_LEVER_Y 84
#define USER_LEVER_RING 29
#define USER_LEVER_KNOB 12
