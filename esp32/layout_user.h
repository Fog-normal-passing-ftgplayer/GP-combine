#pragma once
// GP-Fusion 用户按键布局 — 由 GP-Fusion 配置向导自动生成，请勿手改。
#include "menu.h"

#define USER_LAYOUT 1
#define USER_SHOW_LEVER 1

static const LayoutBtn USER_MOVE[] = {
  {0x00000004, 17, 44, 13, "L", 1, 0},
  {0x00000002, 54, 44, 13, "D", 1, 0},
  {0x00000008, 86, 66, 13, "R", 1, 0},
  {0x00000001, 97, 120, 13, "U", 1, 0},
};

static const LayoutBtn USER_CLUSTER[] = {
  {0x00000004, 120, 54, 13, "X", 0, 0},
  {0x00000008, 150, 45, 13, "Y", 0, 0},
  {0x00000020, 183, 45, 13, "RB", 0, 0},
  {0x00000010, 213, 52, 13, "LB", 0, 0},
  {0x00000001, 120, 89, 13, "A", 0, 0},
  {0x00000002, 150, 78, 13, "B", 0, 0},
  {0x00000040, 181, 81, 13, "RT", 0, 0},
  {0x00000080, 213, 86, 13, "LT", 0, 0},
  {0x00000400, 126, 24, 10, "L3", 0, 1},
  {0x00000800, 124, 119, 10, "R3", 0, 1},
  {0x00002000, 147, 110, 9, "A2", 0, 1},
};

#define USER_LEVER_X 49
#define USER_LEVER_Y 75
#define USER_LEVER_RING 18
#define USER_LEVER_KNOB 11
