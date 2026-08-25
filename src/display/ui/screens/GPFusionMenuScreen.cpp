// GP-Fusion Lite 滑动菜单：设置 / 电池 / 灯光 / 休眠
#include "GPFusionMenuScreen.h"

#include "enums.pb.h"
#include "storagemanager.h"
#include "drivermanager.h"
#include "addons/display.h"
#include "GamepadState.h"
#include "cn_font_lite.h"
#include "fonts/GP_Font_Standard.h"
#include "eventmanager.h"
#include "events/GPStorageSaveEvent.h"
#include "events/GPRestartEvent.h"

#include <cstring>
#include <string>
#include "pico/stdlib.h"

enum OptType { OPT_ENUM, OPT_BOOL, OPT_INT, OPT_ACTION, OPT_SLIDER };

struct LiteOpt {
  const char* label;
  uint8_t type;
  int min, max, step;
  const char* const* names;
  int nameCount;
  const char* unit;
  int (*get)();
  void (*set)(int);
};

struct LiteSection {
  const char* title;
  LiteOpt* opts;
  int count;
};

// ---- config access ----
static GamepadOptions& GOP() { return Storage::getInstance().getGamepadOptions(); }
static DisplayOptions& DOP() { return Storage::getInstance().getDisplayOptions(); }
static AnimationOptions& AOP() { return Storage::getInstance().getAnimationOptions(); }
static LEDOptions& LOP() { return Storage::getInstance().getLedOptions(); }

static void maybeRebootForInputMode();

static const char* const N_INPUT[] = {"XIN","SW","PS3","KBD","PS4","XB1","MDM","NEO",
                                      "PCE","EGR","AST","PSC","XBO","PS5","GEN","SWP","P5G"};
static const char* const N_SOCD[] = {"UP","NEU","2ND","1ST","BYP"};
static const char* const N_DPAD[] = {"DIG","LAN","RAN"};
static const char* const N_ANIM[] = {"静态","彩虹","追逐","主题","自定义","流水"};
static const char* const N_COLOR[] = {"BLK","WHT","RED","ORG","YEL","LME","GRN","SEA",
                                      "AQU","SKY","BLU","PUR","PNK","MAG","IND","VIO"};
static const char* const N_SAVER[] = {"关闭","雪花","弹跳","管道","吐司","MATRIX"};
static const char* const N_LAYOUT[] = {"街机","无摇杆","斜排","直排","键盘"};

static int gInput() { return (int)GOP().inputMode; }
static void sInput(int v) { GOP().inputMode = (InputMode)v; }
static int gSocd() { return (int)GOP().socdMode; }
static void sSocd(int v) { GOP().socdMode = (SOCDMode)v; }
static int gDpad() { return (int)GOP().dpadMode; }
static void sDpad(int v) { GOP().dpadMode = (DpadMode)v; }
static int gFour() { return GOP().fourWayMode ? 1 : 0; }
static void sFour(int v) { GOP().fourWayMode = v ? true : false; }
static int gInvX() { return GOP().invertXAxis ? 1 : 0; }
static void sInvX(int v) { GOP().invertXAxis = v ? true : false; }
static int gInvY() { return GOP().invertYAxis ? 1 : 0; }
static void sInvY(int v) { GOP().invertYAxis = v ? true : false; }
static int gDebounce() { return (int)GOP().debounceDelay; }
static void sDebounce(int v) { GOP().debounceDelay = (uint32_t)v; }
static int gHist() { return DOP().inputHistoryEnabled ? 1 : 0; }
static void sHist(int v) { DOP().inputHistoryEnabled = v ? true : false; }
static int gLayout() { return (int)DOP().buttonLayout; }
static void sLayout(int v) { DOP().buttonLayout = (ButtonLayout)v; }
static int gProfile() { return (int)GOP().profileNumber; }
static void sProfile(int v) { GOP().profileNumber = (uint32_t)v; }
static int gAnim() { return (int)AOP().baseAnimationIndex; }
static void sAnim(int v) { AOP().baseAnimationIndex = (uint32_t)v; }
static int gBright() { return (int)AOP().brightness; }
static void sBright(int v) { AOP().brightness = (uint32_t)v; }
static int gColor() { return (int)AOP().staticColorIndex; }
static void sColor(int v) { AOP().staticColorIndex = (uint32_t)v; }
static int gChase() { int c = (int)AOP().chaseCycleTime; int v = 100 - (c - 1) / 10; return v < 0 ? 0 : (v > 100 ? 100 : v); }
static void sChase(int v) { AOP().chaseCycleTime = (100 - v) * 10 + 1; }
static int gRainbow() { int c = (int)AOP().rainbowCycleTime; int v = 100 - (c - 1) / 10; return v < 0 ? 0 : (v > 100 ? 100 : v); }
static void sRainbow(int v) { AOP().rainbowCycleTime = (100 - v) * 10 + 1; }
static int gFlow() { int c = (int)AOP().flowCycleTime; int v = 100 - (c - 1) / 10; return v < 0 ? 0 : (v > 100 ? 100 : v); }
static void sFlow(int v) { AOP().flowCycleTime = (100 - v) * 10 + 1; }
static int gSaver() { return (int)DOP().displaySaverMode; }
static void sSaver(int v) { DOP().displaySaverMode = (DisplaySaverMode)v; }
// displaySaverTimeout 单位是毫秒，菜单里按秒显示/设置
static int gSaverT() { return (int)(DOP().displaySaverTimeout / 1000); }
static void sSaverT(int v) { DOP().displaySaverTimeout = v * 1000; }
static int gOff() { return DOP().turnOffWhenSuspended ? 1 : 0; }
static void sOff(int v) { DOP().turnOffWhenSuspended = v ? true : false; }
static int gLedOff() { return LOP().turnOffWhenSuspended ? 1 : 0; }
static void sLedOff(int v) { LOP().turnOffWhenSuspended = v ? true : false; }
static int gSave() {
  // 菜单跑在 core1，保存必须通过事件交给 core0 执行
  EventManager::getInstance().triggerEvent(new GPStorageSaveEvent(true));
  maybeRebootForInputMode();
  return 0;
}
static void sSave(int) {}
static int gReset() { Storage::getInstance().ResetSettings(); Storage::getInstance().save(); return 0; }
static void sReset(int) {}

static LiteOpt optHand[] = {
  {"输入模式", OPT_ENUM, 0, 16, 1, N_INPUT, 17, "", gInput, sInput},
  {"SOCD模式", OPT_ENUM, 0, 4, 1, N_SOCD, 5, "", gSocd, sSocd},
  {"D-Pad模式", OPT_ENUM, 0, 2, 1, N_DPAD, 3, "", gDpad, sDpad},
  {"四向模式", OPT_BOOL, 0, 1, 1, NULL, 0, "", gFour, sFour},
  {"反向X", OPT_BOOL, 0, 1, 1, NULL, 0, "", gInvX, sInvX},
  {"反向Y", OPT_BOOL, 0, 1, 1, NULL, 0, "", gInvY, sInvY},
  {"去抖延迟", OPT_INT, 1, 20, 1, NULL, 0, "ms", gDebounce, sDebounce},
};
static LiteOpt optDisp[] = {
  {"输入历史", OPT_BOOL, 0, 1, 1, NULL, 0, "", gHist, sHist},
  {"按键布局", OPT_ENUM, 0, 4, 1, N_LAYOUT, 5, "", gLayout, sLayout},
};
static LiteOpt optSys[] = {
  {"配置档", OPT_INT, 1, 4, 1, NULL, 0, "", gProfile, sProfile},
  {"保存设置", OPT_ACTION, 0, 0, 0, NULL, 0, "", gSave, sSave},
  {"恢复默认", OPT_ACTION, 0, 0, 0, NULL, 0, "", gReset, sReset},
};
static LiteOpt optLed[] = {
  {"动画模式", OPT_ENUM, 0, 5, 1, N_ANIM, 6, "", gAnim, sAnim},
  {"亮度", OPT_INT, 0, 5, 1, NULL, 0, "", gBright, sBright},
  {"静态颜色", OPT_ENUM, 0, 15, 1, N_COLOR, 16, "", gColor, sColor},
  {"追逐速度", OPT_SLIDER, 0, 100, 1, NULL, 0, "", gChase, sChase},
  {"彩虹速度", OPT_SLIDER, 0, 100, 1, NULL, 0, "", gRainbow, sRainbow},
  {"流水速度", OPT_SLIDER, 0, 100, 1, NULL, 0, "", gFlow, sFlow},
  {"挂起关灯", OPT_BOOL, 0, 1, 1, NULL, 0, "", gLedOff, sLedOff},
};
static LiteOpt optSleep[] = {
  {"屏保模式", OPT_ENUM, 0, 5, 1, N_SAVER, 6, "", gSaver, sSaver},
  {"屏保时间", OPT_INT, 0, 600, 10, NULL, 0, "秒", gSaverT, sSaverT},
  {"关屏", OPT_BOOL, 0, 1, 1, NULL, 0, "", gOff, sOff},
};

static LiteSection secSettings[] = {
  {"手柄", optHand, 7},
  {"显示", optDisp, 2},
  {"系统", optSys, 3},
};
static LiteSection secLed[] = {{"彩灯", optLed, 6}};
static LiteSection secSleep[] = {{"休眠", optSleep, 3}};

static const char* const PAGE_TITLES[] = {"设置", "灯光", "休眠"};
static const int NUM_PAGES = 3;

// ---- screen state ----
static int page = 0;
static int level = 0;        // 0=页面 1=分区 2=选项
static int section = 0;
static int sel = 0;
static int scroll = 0;
static bool dirty = false;
static bool confirmOpen = false;
static int confirmChoice = 0;
static int snap[8];
static int lastSavedInputMode = -1;

// 输入模式改了：保存后重启应用（USB 描述符需重启生效）
static void maybeRebootForInputMode() {
  int cur = (int)GOP().inputMode;
  if (cur != lastSavedInputMode) {
    lastSavedInputMode = cur;
    EventManager::getInstance().triggerEvent(new GPRestartEvent(System::BootMode::GAMEPAD));
  }
}

static bool animating = false;
static int animDir = 0;
static unsigned long animStart = 0;
static int animFrom = 0, animTo = 0;
static int oldPage = 0;

// 列表上下滑动动画
static float selY = 0, selYFrom = 0, selYTo = 0;
static float scrollPx = 0, scrollPxFrom = 0, scrollPxTo = 0;
static bool listAnim = false;
static unsigned long listAnimStart = 0;

static uint16_t prevB = 0;
static uint8_t prevD = 0;
static unsigned long lastRepeat = 0;
static uint8_t repeatMask = 0;

static LiteSection* currentSections() {
  switch (page) {
    case 0: return secSettings;
    case 1: return secLed;
    case 2: return secSleep;
    default: return NULL;
  }
}
static int sectionCount() {
  LiteSection* s = currentSections();
  return s ? (page == 0 ? 3 : 1) : 0;
}
static LiteSection& curSection() {
  return currentSections()[section];
}

static void startListAnim(int selIdx, int scrollIdx) {
  selYFrom = selY;
  selYTo = selIdx * 13.0f;
  scrollPxFrom = scrollPx;
  scrollPxTo = scrollIdx * 13.0f;
  listAnimStart = getMillis();
  listAnim = true;
}

static void resetListAnim() {
  selY = 0; selYFrom = 0; selYTo = 0;
  scrollPx = 0; scrollPxFrom = 0; scrollPxTo = 0;
  listAnim = false;
}

static void snapshot() {
  LiteSection& s = curSection();
  for (int i = 0; i < s.count && i < 8; i++) snap[i] = s.opts[i].get();
}
static void restore() {
  LiteSection& s = curSection();
  for (int i = 0; i < s.count && i < 8; i++) s.opts[i].set(snap[i]);
}

// ---- drawing helpers (clipped to 128x64) ----
static GPGFX* R = NULL;
static void px(int x, int y, int c) {
  if (x >= 0 && x < 128 && y >= 0 && y < 64) R->drawPixel(x, y, c);
}
static void fill(int x, int y, int w, int h, int c) {
  for (int yy = y; yy < y + h; yy++)
    for (int xx = x; xx < x + w; xx++) px(xx, yy, c);
}

static void drawAscii(int x, int y, const char* s, int color);

static int findCJK(uint16_t cp) {
  int lo = 0, hi = CN_FONT_NUM - 1;
  while (lo <= hi) {
    int mid = (lo + hi) / 2;
    if (CN_FONT_CODES[mid] == cp) return mid;
    if (CN_FONT_CODES[mid] < cp) lo = mid + 1; else hi = mid - 1;
  }
  return -1;
}

static void drawCJKChar(int x, int y, uint16_t cp, int color) {
  int idx = findCJK(cp);
  if (idx < 0) return;
  const uint8_t* g = CN_FONT_GLYPHS[idx];
  for (int row = 0; row < CN_FONT_SIZE; row++) {
    uint16_t bits = ((uint16_t)g[row * 2] << 8) | g[row * 2 + 1];
    for (int col = 0; col < CN_FONT_SIZE; col++) {
      if (bits & (0x8000 >> col)) px(x + col, y + row, color);
    }
  }
}

static int cjkWidth(const char* s) {
  int w = 0;
  while (*s) {
    uint8_t c = (uint8_t)*s;
    if (c < 0x80) { w += 6; s++; }
    else if ((c & 0xE0) == 0xC0) { w += CN_FONT_SIZE; s += 2; }
    else if ((c & 0xF0) == 0xE0) { w += CN_FONT_SIZE; s += 3; }
    else s++;
  }
  return w;
}

static void drawCJK(int x, int y, const char* s, int color, bool centered = false) {
  if (centered) x -= cjkWidth(s) / 2;
  while (*s) {
    uint8_t c = (uint8_t)*s;
    if (c < 0x80) {
      char buf[2] = {(char)c, 0};
      drawAscii(x, y, buf, color);
      x += 6; s++;
      continue;
    }
    uint16_t cp = 0;
    if ((c & 0xE0) == 0xC0) { cp = ((uint16_t)(c & 0x1F) << 6) | ((uint8_t)*++s & 0x3F); s++; }
    else if ((c & 0xF0) == 0xE0) {
      cp = ((uint16_t)(c & 0x0F) << 12) | (((uint8_t)*++s & 0x3F) << 6);
      cp |= ((uint8_t)*++s & 0x3F); s++;
    } else { s++; continue; }
    drawCJKChar(x, y, cp, color);
    x += CN_FONT_SIZE;
  }
}

static void drawAsciiRight(int rightX, int y, const char* s, int invert) {
  int w = (int)strlen(s) * 6;
  if (rightX - w < 0) return;
  R->drawText(rightX - w, y, std::string(s), invert);
}

// 自绘 ASCII（带颜色：选中高亮行上也不会白字白底）
static void drawAscii(int x, int y, const char* s, int color) {
  while (*s) {
    uint8_t c = (uint8_t)*s;
    if (c >= GPGFX_FONT_CHAR_OFFSET && c < GPGFX_FONT_CHAR_OFFSET + 96) {
      const uint8_t* g = &GP_Font_Standard[(c - GPGFX_FONT_CHAR_OFFSET) * 5];
      for (int col = 0; col < 5; col++) {
        uint8_t byte = g[col];
        for (int row = 0; row < 8; row++) {
          if (byte & (1 << row)) px(x + col, y + row, color);
        }
      }
    }
    x += 6;
    s++;
  }
}

static bool isAsciiStr(const char* s) {
  for (const char* p = s; *p; p++) if ((uint8_t)*p >= 0x80) return false;
  return true;
}

static void drawValue(int rightX, int y, const char* s, int color) {
  if (isAsciiStr(s)) {
    int w = (int)strlen(s) * 6;
    drawAscii(rightX - w, y, s, color);
  }
  else drawCJK(rightX - cjkWidth(s), y, s, color);
}

static void drawDisc(int x, int y, int r, int c) {
  for (int dy = -r; dy <= r; dy++)
    for (int dx = -r; dx <= r; dx++)
      if (dx * dx + dy * dy <= r * r) px(x + dx, y + dy, c);
}

static void drawLine(int x0, int y0, int x1, int y1, int c) {
  int dx = x1 > x0 ? x1 - x0 : x0 - x1;
  int dy = y1 > y0 ? y1 - y0 : y0 - y1;
  int sx = x0 < x1 ? 1 : -1;
  int sy = y0 < y1 ? 1 : -1;
  int err = dx - dy;
  while (true) {
    px(x0, y0, c);
    if (x0 == x1 && y0 == y1) break;
    int e2 = 2 * err;
    if (e2 > -dy) { err -= dy; x0 += sx; }
    if (e2 < dx) { err += dx; y0 += sy; }
  }
}

// 页面图标（单色）
static void iconSettings(int off) {          // 三条滑杆
  int ys[3] = {22, 30, 38};
  int kn[3] = {56, 72, 64};
  for (int i = 0; i < 3; i++) {
    drawLine(44 + off, ys[i], 84 + off, ys[i], 1);
    drawDisc(kn[i] + off, ys[i], 4, 1);
  }
}

static void iconLight(int off) {             // 灯泡
  drawDisc(64 + off, 29, 10, 1);
  drawLine(64 + off, 12, 64 + off, 17, 1);
  drawLine(54 + off, 17, 57 + off, 20, 1);
  drawLine(74 + off, 17, 71 + off, 20, 1);
  fill(59 + off, 39, 10, 5, 1);
  fill(63 + off, 44, 2, 4, 1);
}

static void iconMoon(int off) {              // 月牙 + 星星
  drawDisc(60 + off, 31, 11, 1);
  drawDisc(66 + off, 26, 9, 0);              // 挖出月牙
  drawLine(46 + off, 18, 46 + off, 24, 1);   // 星星 +
  drawLine(43 + off, 21, 49 + off, 21, 1);
  drawLine(78 + off, 38, 78 + off, 44, 1);
  drawLine(75 + off, 41, 81 + off, 41, 1);
}

static void drawPageIcon(int off, int p) {
  switch (p) {
    case 0: iconSettings(off); break;
    case 1: iconLight(off); break;
    case 2: iconMoon(off); break;
  }
}

static const char* optValueText(const LiteOpt* o) {
  static char buf[12];
  int v = o->get();
  if (o->type == OPT_ENUM) {
    int i = v - o->min;
    return (i >= 0 && i < o->nameCount) ? o->names[i] : "?";
  }
  if (o->type == OPT_BOOL) return v ? "开启" : "关闭";
  snprintf(buf, sizeof(buf), "%d%s", v, o->unit);
  return buf;
}

static void drawSlider(int x, int y, int w, int v, int max, int color) {
  fill(x, y + 3, w, 1, color);             // track
  int tw = (max > 0) ? (w - 4) * v / max : 0;
  if (tw > 0) fill(x, y + 3, tw + 2, 1, color);
  fill(x + tw + 1, y + 1, 3, 5, color);    // thumb
}

void GPFusionMenuScreen::init() {
  page = 0; level = 0; section = 0; sel = 0; scroll = 0;
  dirty = false; confirmOpen = false; animating = false;
  resetListAnim();
  lastSavedInputMode = (int)GOP().inputMode;
  prevB = 0; prevD = 0;
  getRenderer()->clearScreen();
}

void GPFusionMenuScreen::shutdown() {
}

static void slideTo(int dir) {
  oldPage = page;
  page = (page + dir + NUM_PAGES) % NUM_PAGES;
  animDir = dir;
  animFrom = dir * 128;
  animTo = 0;
  animStart = getMillis();
  animating = true;
  level = 0; section = 0; sel = 0; scroll = 0;
  resetListAnim();
}

static void backOne() {
  if (level == 2) {
    LiteSection* secs = currentSections();
    if (secs && page == 0) { level = 1; section = 0; sel = 0; scroll = 0; }
    else { level = 0; section = 0; sel = 0; scroll = 0; }
  } else {
    level = 0; section = 0; sel = 0; scroll = 0;
  }
  resetListAnim();
  dirty = false;
}

int8_t GPFusionMenuScreen::update() {
  R = getRenderer();
  Gamepad* gamepad = Storage::getInstance().GetGamepad();
  uint16_t b = gamepad->state.buttons;
  // 用原始物理方向：D-Pad 被设为摇杆模式时 state.dpad 会被清空，菜单就收不到左右
  uint8_t d = gamepad->state.dpadOriginal;
  uint16_t bEdge = b & ~prevB;
  uint8_t dEdge = d & ~prevD;
  bool anyEdge = (bEdge || dEdge);
  prevB = b; prevD = d;
  (void)anyEdge;

  unsigned long now = getMillis();

  // slide animation tick
  if (animating) {
    unsigned long dt = now - animStart;
    if (dt >= 140) {
      animating = false;
    }
  }
  if (listAnim) {
    unsigned long dt = now - listAnimStart;
    float t = (dt >= 140) ? 1.0f : (float)dt / 140.0f;
    float e = 1.0f - (1.0f - t) * (1.0f - t) * (1.0f - t);
    selY = selYFrom + (selYTo - selYFrom) * e;
    scrollPx = scrollPxFrom + (scrollPxTo - scrollPxFrom) * e;
    if (t >= 1.0f) listAnim = false;
  }

  if (confirmOpen) {
    if (dEdge & 0x0C) confirmChoice = 1 - confirmChoice;
    if (bEdge & GAMEPAD_MASK_B1) {
      confirmOpen = false;
      if (confirmChoice == 0) {
        EventManager::getInstance().triggerEvent(new GPStorageSaveEvent(true));
        maybeRebootForInputMode();
        dirty = false;
      } else {
        restore();
        dirty = false;
      }
      backOne();
    } else if (bEdge & GAMEPAD_MASK_B2) {
      confirmOpen = false;
      restore();
      dirty = false;
      backOne();
    }
    return -1;
  }

  // repeat for held up/down/left/right
  uint8_t held = d & 0x0F;
  if (held && now - lastRepeat >= (repeatMask == held ? 160 : 420)) {
    lastRepeat = now;
    repeatMask = held;
    dEdge |= held;   // synthesize repeats
  }
  if (!held) { repeatMask = 0; lastRepeat = 0; }

  if (level == 0) {
    if (dEdge & 0x04) slideTo(-1);   // LEFT
    if (dEdge & 0x08) slideTo(+1);   // RIGHT
    if (bEdge & GAMEPAD_MASK_B1) {   // A enter
      if (sectionCount() > 1) { level = 1; section = 0; sel = 0; scroll = 0; resetListAnim(); }
      else { level = 2; section = 0; sel = 0; scroll = 0; snapshot(); dirty = false; }
    }
    if (bEdge & GAMEPAD_MASK_B2) {   // B exit menu
      return DisplayMode::BUTTONS;
    }
  } else if (level == 1) {
    int cnt = sectionCount();
    if (dEdge & 0x01) sel = (sel + cnt - 1) % cnt;   // UP
    if (dEdge & 0x02) sel = (sel + 1) % cnt;         // DOWN
    if (dEdge & 0x03) startListAnim(sel, 0);
    if (bEdge & GAMEPAD_MASK_B1) { section = sel; level = 2; sel = 0; scroll = 0; resetListAnim(); snapshot(); dirty = false; }
    if (bEdge & GAMEPAD_MASK_B2) { level = 0; sel = 0; resetListAnim(); }
  } else { // options
    LiteSection& s = curSection();
    if (dEdge & 0x01) { // UP（含从顶部回绕到底部）
      sel = (sel == 0) ? s.count - 1 : sel - 1;
      int ts = scroll;
      if (sel < ts) ts = sel;
      if (sel >= ts + 3) ts = sel - 2;
      if (ts > s.count - 3) ts = s.count - 3;
      if (ts < 0) ts = 0;
      scroll = ts;
      startListAnim(sel, scroll);
    }
    if (dEdge & 0x02) { // DOWN（含从底部回绕到顶部）
      sel = (sel + 1) % s.count;
      int ts = scroll;
      if (sel < ts) ts = sel;
      if (sel >= ts + 3) ts = sel - 2;
      if (ts > s.count - 3) ts = s.count - 3;
      if (ts < 0) ts = 0;
      scroll = ts;
      startListAnim(sel, scroll);
    }
    LiteOpt* o = &s.opts[sel];
    if (dEdge & 0x0C) {
      int dir = (dEdge & 0x04) ? -1 : 1;
      if (o->type != OPT_ACTION) {
        int v = o->get() + dir * ((o->type == OPT_INT || o->type == OPT_SLIDER) ? o->step : 1);
        if (v < o->min) v = o->min;
        if (v > o->max) v = o->max;
        o->set(v);
        dirty = true;
      }
    }
    if (bEdge & GAMEPAD_MASK_B1) {
      if (o->type == OPT_ACTION) { o->get(); dirty = false; }
    }
    if (bEdge & GAMEPAD_MASK_B2) {
      if (dirty) { confirmOpen = true; confirmChoice = 0; }
      else backOne();
    }
  }
  return -1;
}

static void drawPagePreview(int p, int off) {
  drawCJK(64 + off, 0, PAGE_TITLES[p], 1, true);
  drawPageIcon(off, p);
  drawCJK(64 + off, 52, "左右切换 A进入 B返回", 1, true);
}

static void drawMenuPages() {
  int off = 0;
  if (animating) {
    unsigned long dt = getMillis() - animStart;
    float t = (dt >= 140) ? 1.0f : (float)dt / 140.0f;
    float e = 1.0f - (1.0f - t) * (1.0f - t) * (1.0f - t);
    off = animFrom + (int)((animTo - animFrom) * e);
  }
  drawPagePreview(page, off);
  if (animating) drawPagePreview(oldPage, off - animDir * 128);
}

static void drawSections() {
  drawCJK(64, 0, "设置", 1, true);
  int cnt = sectionCount();
  fill(0, 13 + (int)selY, 128, 12, 1);
  for (int i = 0; i < cnt; i++) {
    int y = 13 + i * 13;
    drawCJK(8, y, currentSections()[i].title, i == sel ? 0 : 1);
  }
  drawCJK(64, 52, "上下选择 A进入 B返回", 1, true);
}

static void drawOptions() {
  LiteSection& s = curSection();
  drawCJK(64, 0, s.title, 1, true);
  // 选择框要跟随可视区：selY 是绝对位置，减去 scrollPx 才是屏幕上的位置
  fill(0, 13 + (int)(selY - scrollPx), 128, 12, 1);
  for (int i = 0; i < s.count; i++) {
    int y = 13 + i * 13 - (int)scrollPx;
    if (y < 6 || y > 52) continue;
    LiteOpt* o = &s.opts[i];
    drawCJK(2, y, o->label, i == sel ? 0 : 1);
    if (o->type == OPT_SLIDER) {
      drawSlider(70, y + 4, 48, o->get(), o->max, i == sel ? 0 : 1);
    } else {
      if (o->type == OPT_ACTION) drawAscii(122, y + 2, ">", i == sel ? 0 : 1);
      else drawValue(124, y + 2, optValueText(o), i == sel ? 0 : 1);
    }
  }
  // scrollbar
  if (s.count > 3) {
    int th = 40 * 3 / s.count; if (th < 6) th = 6;
    float range = (float)((s.count - 3) * 13);
    int ty = 13 + (range > 0 ? (int)(scrollPx / range * (39 - th)) : 0);
    fill(126, 13, 2, 39, 1);
    fill(126, ty, 2, th, 1);
  }
  drawCJK(64, 52, "左右改值 A确认 B返回", 1, true);
}

void GPFusionMenuScreen::drawScreen() {
  R = getRenderer();
  fill(0, 0, 128, 64, 0);
  if (confirmOpen) {
    fill(24, 18, 80, 36, 0);
    fill(25, 19, 78, 34, 1);
    fill(27, 21, 74, 30, 0);
    drawCJK(64, 24, "是否立即保存", 1, true);
    if (confirmChoice == 0) {
      fill(48, 40, 20, 12, 1);
      drawCJK(58, 40, "是", 0, true);
      drawCJK(82, 40, "否", 1, true);
    } else {
      drawCJK(58, 40, "是", 1, true);
      fill(72, 40, 20, 12, 1);
      drawCJK(82, 40, "否", 0, true);
    }
    drawCJK(64, 55, "左右选择 A确认", 1, true);
    return;
  }
  if (level == 0) drawMenuPages();
  else if (level == 1) drawSections();
  else drawOptions();
}
