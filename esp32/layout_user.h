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
  {0x00000004, 115, 49, 13, "B3", 0, 0},
  {0x00000008, 146, 44, 13, "B4", 0, 0},
  {0x00000020, 179, 43, 13, "R1", 0, 0},
  {0x00000010, 211, 50, 13, "L1", 0, 0},
  {0x00000001, 112, 84, 13, "B1", 0, 0},
  {0x00000002, 142, 78, 13, "B2", 0, 0},
  {0x00000080, 175, 75, 13, "R2", 0, 0},
  {0x00000040, 207, 83, 13, "L2", 0, 0},
  {0x00000400, 116, 117, 13, "L3", 0, 0},
  {0x00000800, 146, 110, 13, "R3", 0, 0},
  {0x00002000, 126, 20, 13, "A2", 0, 0},
};

#define USER_LEVER_X 38
#define USER_LEVER_Y 80
#define USER_LEVER_RING 22
#define USER_LEVER_KNOB 7
