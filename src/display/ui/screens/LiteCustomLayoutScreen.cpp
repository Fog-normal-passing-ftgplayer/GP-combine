// GP-Combine Lite 自定义按键布局屏：顶部状态栏 + 布局形状（读 layout_user.h）
#include "LiteCustomLayoutScreen.h"
#include "storagemanager.h"
#include "drivermanager.h"
#include "GamepadState.h"
#include <cstring>
#include <deque>
#include <string>

// ---- 输入历史（顶部条显示，不缩小布局） ----
static const char* HIST_NAMES[] = {
    "U", "D", "L", "R",
    "B1", "B2", "B3", "B4", "L1", "R1", "L2", "R2",
    "S1", "S2", "L3", "R3", "A1", "A2", "A3", "A4",
};
static std::deque<std::string> histEntries;
static uint32_t histLastMask = 0;
static std::string historyStr;

static void updateInputHistory(Gamepad* g) {
    // 低 4 位 = 原始十字键，其余 = 按键（与 HIST_NAMES 顺序对应）
    uint32_t mask = (uint32_t)(g->state.dpadOriginal & 0x0F);
    mask |= (uint32_t)(g->state.buttons & 0xFFFF) << 4;
    uint32_t newMask = mask & ~histLastMask;
    histLastMask = mask;
    if (newMask == 0) return;

    std::string entry;
    for (int i = 0; i < 20; i++) {
        if (newMask & (1u << i)) {
            if (!entry.empty()) entry += "+";
            entry += HIST_NAMES[i];
        }
    }
    if (entry.empty()) return;
    histEntries.push_back(entry);
    if (histEntries.size() > 8) histEntries.pop_front();

    std::string s;
    for (const auto& e : histEntries) {
        if (!s.empty()) s += " ";
        s += e;
        if (s.size() > 20) {
            s = s.substr(s.size() - 20);
            break;
        }
    }
    historyStr = s;
}

// 布局按钮结构（与配置助手生成的头文件一致）
typedef struct {
    uint32_t mask;
    int16_t x;
    int16_t y;
    uint8_t r;
    const char* label;
    uint8_t dpad;
    uint8_t square;
} LiteLayoutBtn;

#if __has_include("layout_user.h")
#include "layout_user.h"
#else
#define LITE_USER_LAYOUT 0
#define LITE_USER_SHOW_LEVER 0
static const LiteLayoutBtn LITE_USER_MOVE[] = {};
static const LiteLayoutBtn LITE_USER_CLUSTER[] = {};
#define LITE_USER_LEVER_X 38
#define LITE_USER_LEVER_Y 80
#define LITE_USER_LEVER_RING 22
#define LITE_USER_LEVER_KNOB 7
#endif

static const char* modeName() {
    switch (DriverManager::getInstance().getInputMode()) {
        case INPUT_MODE_XINPUT: return "XINPUT";
        case INPUT_MODE_SWITCH: return "SWITCH";
        case INPUT_MODE_PS3: return "PS3";
        case INPUT_MODE_PS4: return "PS4";
        case INPUT_MODE_PS5: return "PS5";
        case INPUT_MODE_P5GENERAL: return "P5G";
        case INPUT_MODE_XBONE: return "XBON";
        case INPUT_MODE_MDMINI: return "GEN/MD";
        case INPUT_MODE_NEOGEO: return "NGMINI";
        case INPUT_MODE_PCEMINI: return "PCE/TG";
        case INPUT_MODE_EGRET: return "EGRET";
        case INPUT_MODE_ASTRO: return "ASTRO";
        case INPUT_MODE_PSCLASSIC: return "PSC";
        case INPUT_MODE_XBOXORIGINAL: return "OGXB";
        case INPUT_MODE_SWITCH_PRO: return "SWPR";
        case INPUT_MODE_KEYBOARD: return "HID-KB";
        case INPUT_MODE_GENERIC: return "USBHID";
        default: return "?";
    }
}

static const char* socdName() {
    switch (Gamepad::resolveSOCDMode(Storage::getInstance().getGamepadOptions())) {
        case SOCD_MODE_NEUTRAL: return "SOCD-N";
        case SOCD_MODE_UP_PRIORITY: return "SOCD-U";
        case SOCD_MODE_SECOND_INPUT_PRIORITY: return "SOCD-L";
        case SOCD_MODE_FIRST_INPUT_PRIORITY: return "SOCD-F";
        case SOCD_MODE_BYPASS: return "SOCD-X";
        default: return "";
    }
}

static void drawLiteBtn(GPGFX* R, const LiteLayoutBtn& b, bool pressed) {
    if (b.square) {
        R->drawRectangle(b.x - b.r, b.y - b.r, b.r * 2, b.r * 2, 1, pressed ? 1 : 0);
    } else {
        R->drawEllipse(b.x, b.y, b.r, b.r, 1, pressed ? 1 : 0);
    }
}

void LiteCustomLayoutScreen::init() {
    getRenderer()->clearScreen();
}

void LiteCustomLayoutScreen::shutdown() {
}

int8_t LiteCustomLayoutScreen::update() {
    Gamepad* g = Storage::getInstance().GetGamepad();
    updateInputHistory(g);
    return -1;
}

void LiteCustomLayoutScreen::drawScreen() {
    GPGFX* R = getRenderer();
    Gamepad* gamepad = Storage::getInstance().GetGamepad();
    uint16_t btns = (uint16_t)(gamepad->state.buttons & 0xFFFF);
    uint8_t d = (uint8_t)gamepad->state.dpad;

    // 顶部条：开启输入历史时显示历史，否则显示 模式 + D-Pad + SOCD
    if (Storage::getInstance().getDisplayOptions().inputHistoryEnabled && !historyStr.empty()) {
        R->drawText(0, 0, historyStr, 0);
    } else {
        std::string status = modeName();
        status += (gamepad->getActiveDpadMode() == DPAD_MODE_LEFT_ANALOG) ? " L" :
                  (gamepad->getActiveDpadMode() == DPAD_MODE_RIGHT_ANALOG) ? " R" : " D";
        status += " ";
        status += socdName();
        R->drawText(0, 0, status, 0);
    }

    for (const LiteLayoutBtn& b : LITE_USER_MOVE) {
        drawLiteBtn(R, b, (b.dpad ? (d & b.mask) : (btns & b.mask)) != 0);
    }
    for (const LiteLayoutBtn& b : LITE_USER_CLUSTER) {
        drawLiteBtn(R, b, (b.dpad ? (d & b.mask) : (btns & b.mask)) != 0);
    }

#if LITE_USER_SHOW_LEVER
    int cx = LITE_USER_LEVER_X;
    int cy = LITE_USER_LEVER_Y;
    int ring = LITE_USER_LEVER_RING;
    int knob = LITE_USER_LEVER_KNOB;
    if (ring < 2) ring = 2;
    if (knob < 1) knob = 1;
    R->drawEllipse(cx, cy, ring, ring, 1, 0);
    int dx = 0, dy = 0;
    if (d & 0x01) dy -= knob;
    if (d & 0x02) dy += knob;
    if (d & 0x04) dx -= knob;
    if (d & 0x08) dx += knob;
    R->drawEllipse(cx + dx, cy + dy, knob, knob, 1, 1);
#endif
}
