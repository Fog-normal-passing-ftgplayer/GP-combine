#pragma once
#include <stdint.h>

// sub-page option model (types must live in a header so Arduino's
// auto-generated prototypes can see them)
enum OptType { OPT_ENUM, OPT_INT, OPT_BOOL, OPT_ACTION, OPT_SLIDER };

struct MenuOpt {
  const char *label;           // Chinese label
  uint8_t type;
  int16_t value;               // current value
  int16_t min, max, step;
  const char *const *names;    // OPT_ENUM: Chinese labels ordered by value
  int nameCount;
  const char *unit;            // OPT_INT: e.g. "秒"
};

#define MAX_SUB_OPTS 8
struct MenuSection {
  const char *title;           // Chinese section title
  MenuOpt *opts;
  int count;
};
struct SubPageDef {
  MenuSection *sections;
  int sectionCount;
};

// one button in a layout view (mask + position + label)
struct LayoutBtn {
  uint32_t mask;
  int16_t x, y, r;
  const char *label;
  uint8_t dpad; // 1 = dpad bit, 0 = gamepad button bit
  uint8_t square; // 1 = square button, 0 = circle
};
