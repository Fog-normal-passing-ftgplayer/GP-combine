#pragma once
// GP-Fusion 用户按键布局 — 由 GP-Fusion 配置向导自动生成，请勿手改。
#include "menu.h"

#define USER_LAYOUT 1
#define USER_SHOW_LEVER 0

static const LayoutBtn USER_MOVE[] = {
  {0x00000004, 17, 44, 13, "L", 1, 0},
  {0x00000002, 54, 45, 13, "D", 1, 0},
  {0x00000008, 86, 66, 13, "R", 1, 0},
  {0x00000001, 103, 109, 14, "U", 1, 0},
};

static const LayoutBtn USER_CLUSTER[] = {
  {0x00000004, 120, 45, 13, "X", 0, 0},
  {0x00000008, 150, 30, 13, "Y", 0, 0},
  {0x00000020, 181, 32, 13, "RB", 0, 0},
  {0x00000010, 213, 34, 13, "LB", 0, 0},
  {0x00000001, 118, 77, 13, "A", 0, 0},
  {0x00000002, 146, 63, 13, "B", 0, 0},
  {0x00000080, 178, 65, 13, "RT", 0, 0},
  {0x00000040, 209, 66, 13, "LT", 0, 0},
  {0x00000100, 203, 120, 7, "S1", 0, 0},
  {0x00000200, 221, 120, 7, "S2", 0, 0},
};

#define USER_LEVER_X 49
#define USER_LEVER_Y 75
#define USER_LEVER_RING 18
#define USER_LEVER_KNOB 11
