// ESP32 菜单 UI 的宿主机仿真器（Windows 版）。
//
// 做法：把 arduino-cli 生成的 sketch/*.ino.cpp 原样 #include 进来 —— 那份文件已经
// 带好 Arduino 自动插入的函数原型，所以真机源码一个字都不用改。我们只提供平台
// API（时钟 / 引脚 / SPI / LittleFS / FreeRTOS），不碰任何 UI 逻辑。
//
// 输入走真实路径：拼出和有线端 Pico 完全一样的 19 字节 INPUT 帧（magic/ver/type/
// len/13B 载荷/CRC16），一个字节一个字节喂给 handleRxByte()，于是菜单、滑条、
// 屏保唤醒、长按 S2 全走固件自己的代码。
//
// 两种模式：
//   keys    键盘实时操作（Win32 GetAsyncKeyState 读真实按下/松开，长按才成立）
//           上/下/左/右 = 方向键，1 = S2，2 = S1，z = A，x = B
//   script  脚本化确定性回放，用于出截图/动图
//
// 与 Linux 版的唯一差异是平台后端：X11 窗口/键盘 → Win32；zlib PNG → GDI+ 存图；
// clock_gettime → QueryPerformanceCounter；业务帧协议、CLI 参数、巡演脚本格式完全不变。

// Win32/GDI+ 头必须在固件（Arduino.h 会定义 INPUT/OUTPUT 等宏）之前引入，
// 否则 Arduino 宏会污染 winuser.h 里的 INPUT 结构体名。
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#include <objidl.h>
#include <conio.h>
#include <gdiplus.h>
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "gdiplus.lib")
#else
#include <sys/stat.h>
#include <termios.h>
#include <unistd.h>
#include <fcntl.h>
#include <time.h>
#include <dirent.h>     // POSIX 分支遍历目录要用（Windows 分支走 FindFirstFile）
#include <zlib.h>
#include <X11/Xlib.h>
#include <X11/keysym.h>
#endif

#include "esp32.ino.cpp"   // 由 build.bat 从 arduino-cli 的产物复制到 build/gen/

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <cstdarg>
#include <string>
#include <vector>

// ---------------------------------------------------------------------------
// 平台实现（唯一的时间来源是假时钟）
// ---------------------------------------------------------------------------
static uint64_t g_us = 0;

uint32_t millis() { return (uint32_t)(g_us / 1000ULL); }
uint32_t micros() { return (uint32_t)g_us; }
void delay(uint32_t ms) { g_us += (uint64_t)ms * 1000ULL; }
void delayMicroseconds(uint32_t us) { g_us += (uint64_t)us; }

void pinMode(uint8_t, uint8_t) {}
void digitalWrite(uint8_t, uint8_t) {}
int  digitalRead(uint8_t) { return HIGH; }

bool ledcAttach(uint8_t, uint32_t, uint8_t) { return true; }
bool ledcWrite(uint8_t, uint32_t) { return true; }

uint16_t analogRead(uint8_t) { return 2048; }

SPIClass SPI(0);
SimSerial Serial;

static std::string g_fsRoot = "fs";
SimLittleFS LittleFS;

static std::string simPath(const char *path) {
    std::string p = path ? path : "";
    if (!p.empty() && p[0] == '/') p = p.substr(1);
#ifdef _WIN32
    for (auto &c : p) if (c == '/') c = '\\';
    return g_fsRoot.empty() ? p : g_fsRoot + "\\" + p;
#else
    return g_fsRoot + "/" + p;
#endif
}

bool SimLittleFS::exists(const char *path) {
#ifdef _WIN32
    DWORD attr = GetFileAttributesA(simPath(path).c_str());
    return attr != INVALID_FILE_ATTRIBUTES;
#else
    struct stat st;
    return ::stat(simPath(path).c_str(), &st) == 0;
#endif
}

File SimLittleFS::open(const char *path, const char *mode) {
    std::string full = simPath(path);
#ifdef _WIN32
    DWORD attr = GetFileAttributesA(full.c_str());
    if (attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY)) {
        WIN32_FIND_DATAA *fd = (WIN32_FIND_DATAA *)std::malloc(sizeof(WIN32_FIND_DATAA));
        HANDLE h = FindFirstFileA((full + "\\*").c_str(), fd);
        if (h != INVALID_HANDLE_VALUE) return File(h, fd, full);
        std::free(fd);
        return File();
    }
    FILE *fp = std::fopen(full.c_str(), mode ? mode : "r");
    return File(fp);
#else
    struct stat st;
    if (::stat(full.c_str(), &st) == 0 && S_ISDIR(st.st_mode)) {
        DIR *d = ::opendir(full.c_str());
        return File(d, nullptr, full);
    }
    FILE *fp = std::fopen(full.c_str(), mode ? mode : "r");
    return File(fp);
#endif
}

// ---------------- File 平台实现 ----------------
#ifdef _WIN32

File::File() {}
File::File(FILE *fp) : fp_(fp) {}
File::File(void *dirHandle, void *findData, const std::string &path)
    : dir_(dirHandle), fd_(findData), path_(path) {}
File::File(File &&o) noexcept
    : fp_(o.fp_), dir_(o.dir_), fd_(o.fd_), path_(std::move(o.path_)), name_(std::move(o.name_)) {
    o.fp_ = nullptr; o.dir_ = nullptr; o.fd_ = nullptr;
}
File &File::operator=(File &&o) noexcept {
    if (this != &o) {
        close();
        fp_ = o.fp_; dir_ = o.dir_; fd_ = o.fd_;
        path_ = std::move(o.path_); name_ = std::move(o.name_);
        o.fp_ = nullptr; o.dir_ = nullptr; o.fd_ = nullptr;
    }
    return *this;
}
File::~File() { close(); }

File::operator bool() const { return fp_ != nullptr || (dir_ != nullptr && dir_ != INVALID_HANDLE_VALUE); }
bool File::isDirectory() const { return dir_ != nullptr && dir_ != INVALID_HANDLE_VALUE; }
const char *File::name() const { return name_.c_str(); }

File File::openNextFile() {
    if (dir_ == nullptr || dir_ == INVALID_HANDLE_VALUE) return File();
    WIN32_FIND_DATAA *fd = (WIN32_FIND_DATAA *)fd_;
    bool have = true;
    while (true) {
        if (!have) {
            if (!FindNextFileA((HANDLE)dir_, fd)) return File();
        }
        have = false;
        std::string n = fd->cFileName;
        if (n == "." || n == "..") continue;
        std::string child = path_ + "\\" + n;
        if (fd->dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) {
            WIN32_FIND_DATAA *subfd = (WIN32_FIND_DATAA *)std::malloc(sizeof(WIN32_FIND_DATAA));
            HANDLE h = FindFirstFileA((child + "\\*").c_str(), subfd);
            if (h == INVALID_HANDLE_VALUE) { std::free(subfd); return File(); }
            File f(h, subfd, child);
            f.name_ = n;
            return f;
        }
        FILE *fp = std::fopen(child.c_str(), "r");
        if (!fp) return File();
        File f(fp);
        f.name_ = n;
        return f;
    }
}

int File::available() {
    if (!fp_) return 0;
    long cur = std::ftell(fp_);
    std::fseek(fp_, 0, SEEK_END);
    long end = std::ftell(fp_);
    std::fseek(fp_, cur, SEEK_SET);
    return (int)(end - cur);
}
int File::read() { return fp_ ? std::fgetc(fp_) : -1; }
size_t File::read(uint8_t *buf, size_t len) { return fp_ ? std::fread(buf, 1, len, fp_) : 0; }

String File::readStringUntil(char delim) {
    std::string out;
    if (!fp_) return String();
    int c;
    while ((c = std::fgetc(fp_)) != EOF) {
        if ((char)c == delim) break;
        out.push_back((char)c);
    }
    return String(out);
}

size_t File::size() {
    if (!fp_) return 0;
    long cur = std::ftell(fp_);
    std::fseek(fp_, 0, SEEK_END);
    long end = std::ftell(fp_);
    std::fseek(fp_, cur, SEEK_SET);
    return end < 0 ? 0 : (size_t)end;
}

int File::printf(const char *fmt, ...) {
    if (!fp_) return 0;
    va_list ap;
    va_start(ap, fmt);
    int n = std::vfprintf(fp_, fmt, ap);
    va_end(ap);
    return n;
}
void File::flush() { if (fp_) std::fflush(fp_); }

void File::close() {
    if (fp_) { std::fclose(fp_); fp_ = nullptr; }
    if (dir_ != nullptr && dir_ != INVALID_HANDLE_VALUE) { FindClose((HANDLE)dir_); dir_ = INVALID_HANDLE_VALUE; }
    if (fd_) { std::free(fd_); fd_ = nullptr; }
}

#else

File::File() {}
File::File(FILE *fp) : fp_(fp) {}
File::File(void *dirHandle, void *, const std::string &path) : dir_(dirHandle), path_(path) {}
File::File(File &&o) noexcept
    : fp_(o.fp_), dir_(o.dir_), fd_(o.fd_), path_(std::move(o.path_)), name_(std::move(o.name_)) {
    o.fp_ = nullptr; o.dir_ = nullptr; o.fd_ = nullptr;
}
File &File::operator=(File &&o) noexcept {
    if (this != &o) {
        close();
        fp_ = o.fp_; dir_ = o.dir_; fd_ = o.fd_;
        path_ = std::move(o.path_); name_ = std::move(o.name_);
        o.fp_ = nullptr; o.dir_ = nullptr; o.fd_ = nullptr;
    }
    return *this;
}
File::~File() { close(); }

File::operator bool() const { return fp_ != nullptr || dir_ != nullptr; }
bool File::isDirectory() const { return dir_ != nullptr; }
const char *File::name() const { return name_.c_str(); }

File File::openNextFile() {
    if (!dir_) return File();
    struct dirent *e;
    while ((e = ::readdir((DIR *)dir_)) != nullptr) {
        std::string n = e->d_name;
        if (n == "." || n == "..") continue;
        std::string child = path_ + "/" + n;
        struct stat st;
        if (::stat(child.c_str(), &st) == 0 && S_ISDIR(st.st_mode)) {
            DIR *d = ::opendir(child.c_str());
            if (!d) return File();
            File f(d, nullptr, child);
            f.name_ = n;
            return f;
        }
        FILE *fp = std::fopen(child.c_str(), "r");
        if (!fp) return File();
        File f(fp);
        f.name_ = n;
        return f;
    }
    return File();
}

int File::available() {
    if (!fp_) return 0;
    long cur = std::ftell(fp_);
    std::fseek(fp_, 0, SEEK_END);
    long end = std::ftell(fp_);
    std::fseek(fp_, cur, SEEK_SET);
    return (int)(end - cur);
}
int File::read() { return fp_ ? std::fgetc(fp_) : -1; }
size_t File::read(uint8_t *buf, size_t len) { return fp_ ? std::fread(buf, 1, len, fp_) : 0; }

String File::readStringUntil(char delim) {
    std::string out;
    if (!fp_) return String();
    int c;
    while ((c = std::fgetc(fp_)) != EOF) {
        if ((char)c == delim) break;
        out.push_back((char)c);
    }
    return String(out);
}

size_t File::size() {
    if (!fp_) return 0;
    long cur = std::ftell(fp_);
    std::fseek(fp_, 0, SEEK_END);
    long end = std::ftell(fp_);
    std::fseek(fp_, cur, SEEK_SET);
    return end < 0 ? 0 : (size_t)end;
}

int File::printf(const char *fmt, ...) {
    if (!fp_) return 0;
    va_list ap;
    va_start(ap, fmt);
    int n = std::vfprintf(fp_, fmt, ap);
    va_end(ap);
    return n;
}
void File::flush() { if (fp_) std::fflush(fp_); }

void File::close() {
    if (fp_) { std::fclose(fp_); fp_ = nullptr; }
    if (dir_) { ::closedir((DIR *)dir_); dir_ = nullptr; }
}

#endif

// ---------------------------------------------------------------------------
// 画面尺寸
// ---------------------------------------------------------------------------
#ifndef SIM_IMG_W
#define SIM_IMG_W 240
#define SIM_IMG_H 135
#endif

#ifdef SCR_W
static const int IMG_W = SCR_W;
static const int IMG_H = SCR_H;
#else
static const int IMG_W = SIM_IMG_W;
static const int IMG_H = SIM_IMG_H;
#endif

#ifdef SCR_W
static_assert(IMG_W == SCR_W && IMG_H == SCR_H,
              "IMG_W/IMG_H 与固件 SCR_W/SCR_H 不符：build.bat 里的 -DSIM_IMG_W/H 传错了");
#endif

// esp32_172x320 因为内部 DRAM 余量不足，把 lfb 改成了 setup() 里从 PSRAM 堆分配的
// 指针（其它变体是数组）。指针版编译期无法校验，所以 boot 之后要再查一次，
// 否则分配失败会直接踩空指针。
static inline bool lfbReady() { return lfb != nullptr; }

// ---------------------------------------------------------------------------
// PNG 输出（Windows: GDI+ 直接存 PNG；POSIX: 手写块结构 + zlib）
// ---------------------------------------------------------------------------
static bool mkdirs(const std::string &path) {
    std::string cur;
    for (size_t i = 0; i <= path.size(); i++) {
        if (i == path.size() || path[i] == '/' || path[i] == '\\') {
            if (!cur.empty() && cur != "." && cur != ".."
#ifdef _WIN32
                && cur != "\\"
#else
                && cur != "/"
#endif
               ) {
#ifdef _WIN32
                CreateDirectoryA(cur.c_str(), nullptr);
#else
                ::mkdir(cur.c_str(), 0755);
#endif
            }
            if (i == path.size()) break;
        }
        if (i < path.size()) cur.push_back(path[i]);
    }
#ifdef _WIN32
    DWORD attr = GetFileAttributesA(path.c_str());
    return attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY);
#else
    struct stat st;
    return ::stat(path.c_str(), &st) == 0 && S_ISDIR(st.st_mode);
#endif
}

#ifdef _WIN32

static int getEncoderClsid(const WCHAR *format, CLSID *pClsid) {
    UINT num = 0, size = 0;
    Gdiplus::GetImageEncodersSize(&num, &size);
    if (size == 0) return -1;
    std::vector<uint8_t> buf(size);
    Gdiplus::ImageCodecInfo *pInfo = (Gdiplus::ImageCodecInfo *)buf.data();
    Gdiplus::GetImageEncoders(num, size, pInfo);
    for (UINT i = 0; i < num; i++) {
        if (wcscmp(pInfo[i].MimeType, format) == 0) {
            *pClsid = pInfo[i].Clsid;
            return (int)i;
        }
    }
    return -1;
}

static bool writePng(const std::string &path) {
    if (!lfb) return false;
    using namespace Gdiplus;
    Bitmap bmp(IMG_W, IMG_H, PixelFormat24bppRGB);
    BitmapData bd;
    Rect rc(0, 0, IMG_W, IMG_H);
    if (bmp.LockBits(&rc, ImageLockModeWrite, PixelFormat24bppRGB, &bd) != Ok) return false;
    for (int y = 0; y < IMG_H; y++) {
        uint8_t *row = (uint8_t *)bd.Scan0 + (size_t)y * bd.Stride;
        for (int x = 0; x < IMG_W; x++) {
            uint16_t c = lfb[y * IMG_W + x];
            uint8_t r5 = (uint8_t)((c >> 11) & 0x1F);
            uint8_t g6 = (uint8_t)((c >> 5) & 0x3F);
            uint8_t b5 = (uint8_t)(c & 0x1F);
            row[x * 3 + 2] = (uint8_t)((r5 * 255 + 15) / 31);
            row[x * 3 + 1] = (uint8_t)((g6 * 255 + 31) / 63);
            row[x * 3 + 0] = (uint8_t)((b5 * 255 + 15) / 31);
        }
    }
    bmp.UnlockBits(&bd);

    CLSID clsid;
    if (getEncoderClsid(L"image/png", &clsid) < 0) return false;
    // 路径可能含中文：argv 经 CRT 按系统 ANSI 码页（GBK）传入，按 ACP 转 UTF-16，不能逐字节扩
    int wn = MultiByteToWideChar(CP_ACP, 0, path.c_str(), -1, nullptr, 0);
    if (wn <= 0) return false;
    std::wstring wpath(wn, L'\0');
    MultiByteToWideChar(CP_ACP, 0, path.c_str(), -1, &wpath[0], wn);
    return bmp.Save(wpath.c_str(), &clsid) == Ok;
}

#else

static void pngChunk(FILE *f, const char type[4], const uint8_t *data, size_t n) {
    uint8_t len[4] = {(uint8_t)(n >> 24), (uint8_t)(n >> 16), (uint8_t)(n >> 8), (uint8_t)n};
    std::fwrite(len, 1, 4, f);
    std::fwrite(type, 1, 4, f);
    if (n) std::fwrite(data, 1, n, f);
    uint32_t c = (uint32_t)::crc32(0, (const Bytef *)type, 4);
    if (n) c = (uint32_t)::crc32(c, (const Bytef *)data, n);
    uint8_t cb[4] = {(uint8_t)(c >> 24), (uint8_t)(c >> 16), (uint8_t)(c >> 8), (uint8_t)c};
    std::fwrite(cb, 1, 4, f);
}

static bool writePng(const std::string &path) {
    std::vector<uint8_t> raw((size_t)IMG_H * (1 + (size_t)IMG_W * 3));
    size_t o = 0;
    for (int y = 0; y < IMG_H; y++) {
        raw[o++] = 0;
        for (int x = 0; x < IMG_W; x++) {
            uint16_t c = lfb[y * IMG_W + x];
            uint8_t r5 = (uint8_t)((c >> 11) & 0x1F);
            uint8_t g6 = (uint8_t)((c >> 5) & 0x3F);
            uint8_t b5 = (uint8_t)(c & 0x1F);
            raw[o++] = (uint8_t)((r5 * 255 + 15) / 31);
            raw[o++] = (uint8_t)((g6 * 255 + 31) / 63);
            raw[o++] = (uint8_t)((b5 * 255 + 15) / 31);
        }
    }
    uLongf cap = compressBound((uLong)raw.size());
    std::vector<uint8_t> comp(cap);
    if (compress2(comp.data(), &cap, raw.data(), (uLong)raw.size(), 1) != Z_OK) return false;
    comp.resize(cap);

    FILE *f = std::fopen(path.c_str(), "wb");
    if (!f) return false;
    static const uint8_t sig[8] = {0x89, 'P', 'N', 'G', '\r', '\n', 0x1A, '\n'};
    std::fwrite(sig, 1, 8, f);
    uint8_t ihdr[13];
    ihdr[0] = (uint8_t)(IMG_W >> 24); ihdr[1] = (uint8_t)(IMG_W >> 16);
    ihdr[2] = (uint8_t)(IMG_W >> 8);  ihdr[3] = (uint8_t)(IMG_W);
    ihdr[4] = (uint8_t)(IMG_H >> 24); ihdr[5] = (uint8_t)(IMG_H >> 16);
    ihdr[6] = (uint8_t)(IMG_H >> 8);  ihdr[7] = (uint8_t)(IMG_H);
    ihdr[8] = 8;  // bit depth
    ihdr[9] = 2;  // color type: truecolor RGB
    ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
    pngChunk(f, "IHDR", ihdr, sizeof(ihdr));
    pngChunk(f, "IDAT", comp.data(), comp.size());
    pngChunk(f, "IEND", nullptr, 0);
    std::fclose(f);
    return true;
}

#endif

// 只有画面真的变了才写盘（172 版 lfb 是 setup 里分配的指针，长度按 IMG 尺寸算）
static uint64_t hashLfb() {
    const uint8_t *p = (const uint8_t *)lfb;
    size_t bytes = (size_t)IMG_W * IMG_H * sizeof(uint16_t);
    uint64_t h = 1469598103934665603ULL;
    for (size_t i = 0; i < bytes; i++) { h ^= p[i]; h *= 1099511628211ULL; }
    return h;
}

// ---------------------------------------------------------------------------
// 输入注入：拼出和有线端 Pico 完全一致的 19 字节 INPUT 帧
// ---------------------------------------------------------------------------
static uint16_t g_prevButtons = 0xFFFF;   // 保证第一帧一定发出去
static uint8_t  g_prevDpad    = 0xFF;
static uint32_t g_lastSendMs  = 0;

static void sendInputFrame(uint16_t buttons, uint8_t dpad) {
    uint8_t f[19];
    f[0] = FRAME_MAGIC;
    f[1] = FRAME_VERSION;
    f[2] = FRAME_TYPE_INPUT;
    f[3] = 13;                       // buttons(2) dpad(1) lx/ly/rx/ry(8) lt/rt(2)
    f[4] = (uint8_t)(buttons & 0xFF);
    f[5] = (uint8_t)(buttons >> 8);
    f[6] = dpad;
    f[7] = 0x00; f[8] = 0x80;        // lx = 0x8000（居中）
    f[9] = 0x00; f[10] = 0x80;       // ly
    f[11] = 0x00; f[12] = 0x80;      // rx
    f[13] = 0x00; f[14] = 0x80;      // ry
    f[15] = 0;                       // lt
    f[16] = 0;                       // rt
    uint16_t crc = 0xFFFF;
    for (int i = 1; i <= 16; i++) crc = crc16_update(crc, f[i]);
    f[17] = (uint8_t)(crc & 0xFF);
    f[18] = (uint8_t)(crc >> 8);
    for (int i = 0; i < 19; i++) handleRxByte(f[i]);
}

// STATUS 帧：状态栏和电池页的数据来源（真机上由 Pico 的 uart_link 发）。
// 不注入的话电池页会显示 0.00V —— 那不是 bug，是"没接到 Pico"。
static uint32_t g_lastStatusMs = 0xFFFFFFFFu;

static void sendStatusFrame() {
    const uint8_t n = 18;
    uint8_t f[4 + n + 2];
    f[0] = FRAME_MAGIC; f[1] = FRAME_VERSION; f[2] = FRAME_TYPE_STATUS; f[3] = n;
    uint8_t *p = f + 4;
    p[0] = 0;    // socdMode: UP
    p[1] = 0;    // dpadMode: DIGITAL
    p[2] = 0;    // inputMode: XINPUT
    p[3] = 0;    // flags
    p[4] = 5;    // debounceDelay
    p[5] = 1;    // animIndex
    p[6] = 3;    // brightness
    p[7] = 1;    // staticColor
    p[8] = 100 & 0xFF; p[9] = 100 >> 8;    // chaseCycle
    p[10] = 100 & 0xFF; p[11] = 100 >> 8;  // rainbowCycle
    p[12] = 1;                             // ledFlags
    p[13] = 100 & 0xFF; p[14] = 100 >> 8;  // flowCycle
    p[15] = 4150 & 0xFF; p[16] = 4150 >> 8;  // battMv
    p[17] = 0x03;                          // battFlags: 有效 + USB 供电
    uint16_t crc = 0xFFFF;
    for (int i = 1; i < 4 + n; i++) crc = crc16_update(crc, f[i]);
    f[4 + n] = (uint8_t)(crc & 0xFF);
    f[5 + n] = (uint8_t)(crc >> 8);
    for (int i = 0; i < 4 + n + 2; i++) handleRxByte(f[i]);
}

// 变化立即发 + 50ms 心跳（和真机 uart_link 的策略一致）
static void feedInput(uint16_t buttons, uint8_t dpad) {
    uint32_t now = millis();
    if (g_lastStatusMs == 0xFFFFFFFFu || now - g_lastStatusMs >= 1000) {
        sendStatusFrame();
        g_lastStatusMs = now;
    }
    if (buttons != g_prevButtons || dpad != g_prevDpad || now - g_lastSendMs >= 50) {
        sendInputFrame(buttons, dpad);
        g_prevButtons = buttons;
        g_prevDpad = dpad;
        g_lastSendMs = now;
    }
}

// ---------------------------------------------------------------------------
// 键盘：Win32 读真实按下/松开；无窗口时退化为控制台 _kbhit 路径
// ---------------------------------------------------------------------------
struct SimIn { uint16_t buttons = 0; uint8_t dpad = 0; };

// 位掩码（与固件一致）
static const uint16_t BTN_A  = 0x0001;   // B1
static const uint16_t BTN_B  = 0x0002;   // B2
static const uint16_t BTN_S1 = 0x0100;
static const uint16_t BTN_S2 = 0x0200;
static const uint8_t  DP_UP = 0x01, DP_DOWN = 0x02, DP_LEFT = 0x04, DP_RIGHT = 0x08;

#ifdef _WIN32

class WinKeys {
public:
    bool init() { return true; }
    void focusWindow(HWND h) { hwnd_ = h; }

    bool hasFocus() {
        if (!hwnd_) return true;
        return GetForegroundWindow() == hwnd_;
    }

    bool quitRequested() {
        return (GetAsyncKeyState(VK_ESCAPE) & 0x8000) != 0;
    }

    // 返回 false 表示连接断了（Win32 不会断）
    bool poll(SimIn &in) {
        // 只有仿真窗口拿到焦点时才采键：否则在聊天框里打字也会把菜单乱翻
        if (!hasFocus()) { in.buttons = 0; in.dpad = 0; return true; }
        auto held = [](int vk) -> bool {
            return (GetAsyncKeyState(vk) & 0x8000) != 0;
        };
        in.dpad = 0;
        if (held(VK_UP))    in.dpad |= DP_UP;
        if (held(VK_DOWN))  in.dpad |= DP_DOWN;
        if (held(VK_LEFT))  in.dpad |= DP_LEFT;
        if (held(VK_RIGHT)) in.dpad |= DP_RIGHT;
        in.buttons = 0;
        if (held('1')) in.buttons |= BTN_S2;   // 1 -> S2
        if (held('2')) in.buttons |= BTN_S1;   // 2 -> S1
        if (held('Z')) in.buttons |= BTN_A;    // z -> A
        if (held('X')) in.buttons |= BTN_B;    // x -> B
        return true;
    }

private:
    HWND hwnd_ = nullptr;
};

// 控制台退化路径：终端只给“按下”不给“松开”，所以只能靠重复字节维持按住状态。
// 长按（比如 S2 三秒进菜单）在这条路上不成立 —— 开窗口才有真实松开事件。
class ConsoleKeys {
public:
    bool init() { return true; }

    bool poll(SimIn &in) {
        uint32_t now = millis();
        while (_kbhit()) {
            int c = _getch();
            if (c == 0 || c == 0xE0) {
                int a = _getch();
                switch (a) {
                    case 72: upT_    = now; break;
                    case 80: downT_  = now; break;
                    case 77: rightT_ = now; break;
                    case 75: leftT_  = now; break;
                }
            } else if (c == '1') { s2T_ = now; }
            else if (c == '2') { s1T_ = now; }
            else if (c == 'z' || c == 'Z') { aT_ = now; }
            else if (c == 'x' || c == 'X') { bT_ = now; }
        }
        const uint32_t HOLD = 220;   // 按下保持窗口：太短单步会漏，太长单次会连走
        in.dpad = 0;
        if (now - upT_    < HOLD) in.dpad |= DP_UP;
        if (now - downT_  < HOLD) in.dpad |= DP_DOWN;
        if (now - leftT_  < HOLD) in.dpad |= DP_LEFT;
        if (now - rightT_ < HOLD) in.dpad |= DP_RIGHT;
        in.buttons = 0;
        if (now - s2T_ < HOLD) in.buttons |= BTN_S2;
        if (now - s1T_ < HOLD) in.buttons |= BTN_S1;
        if (now - aT_  < HOLD) in.buttons |= BTN_A;
        if (now - bT_  < HOLD) in.buttons |= BTN_B;
        return true;
    }

private:
    uint32_t upT_ = 0, downT_ = 0, leftT_ = 0, rightT_ = 0;
    uint32_t s2T_ = 0, s1T_ = 0, aT_ = 0, bT_ = 0;
};

// ---------------------------------------------------------------------------
// Win32 显示窗口
// ---------------------------------------------------------------------------
static HWND g_simHwnd = nullptr;
static bool g_simAlive = true;

static LRESULT CALLBACK simWndProc(HWND h, UINT msg, WPARAM w, LPARAM l) {
    switch (msg) {
        case WM_CLOSE:
            g_simAlive = false;
            DestroyWindow(h);
            return 0;
        case WM_DESTROY:
            g_simAlive = false;
            PostQuitMessage(0);
            return 0;
        default:
            return DefWindowProcW(h, msg, w, l);
    }
}

class Win32Window {
public:
    bool open(int scale, const wchar_t *title) {
        scale_ = scale < 1 ? 1 : scale;
        w_ = IMG_W * scale_;
        h_ = IMG_H * scale_;

        HINSTANCE inst = GetModuleHandle(nullptr);
        static bool registered = false;
        if (!registered) {
            WNDCLASSEXW wc{};
            wc.cbSize = sizeof(wc);
            wc.lpfnWndProc = simWndProc;
            wc.hInstance = inst;
            wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
            wc.lpszClassName = L"GPCombineSimWnd";
            RegisterClassExW(&wc);
            registered = true;
        }

        RECT rc{0, 0, w_, h_};
        AdjustWindowRect(&rc, WS_OVERLAPPEDWINDOW, FALSE);
        int winW = rc.right - rc.left;
        int winH = rc.bottom - rc.top;

        hwnd_ = CreateWindowExW(0, L"GPCombineSimWnd", title,
                                WS_OVERLAPPEDWINDOW,
                                CW_USEDEFAULT, CW_USEDEFAULT, winW, winH,
                                nullptr, nullptr, inst, nullptr);
        if (!hwnd_) return false;
        g_simHwnd = hwnd_;

        HDC screen = GetDC(nullptr);
        BITMAPINFO bi{};
        bi.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
        bi.bmiHeader.biWidth = w_;
        bi.bmiHeader.biHeight = -h_;   // 顶向下，行序和 lfb 一致
        bi.bmiHeader.biPlanes = 1;
        bi.bmiHeader.biBitCount = 32;
        bi.bmiHeader.biCompression = BI_RGB;
        void *bits = nullptr;
        bmp_ = CreateDIBSection(screen, &bi, DIB_RGB_COLORS, &bits, nullptr, 0);
        ReleaseDC(nullptr, screen);
        if (!bmp_ || !bits) return false;
        buf_ = (uint32_t *)bits;

        // RGB565 -> 32bpp BGRA 的查表，避免每帧重复算
        for (int c = 0; c < 65536; c++) {
            uint32_t r = (uint32_t)(((c >> 11) & 0x1F) * 255 + 15) / 31;
            uint32_t g = (uint32_t)(((c >> 5) & 0x3F) * 255 + 31) / 63;
            uint32_t b = (uint32_t)((c & 0x1F) * 255 + 15) / 31;
            lut_[c] = 0xFF000000u | (r << 16) | (g << 8) | b;
        }

        ShowWindow(hwnd_, SW_SHOW);
        UpdateWindow(hwnd_);
        dirty_ = true;
        return true;
    }

    bool alive() {
        MSG msg;
        while (PeekMessage(&msg, nullptr, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_QUIT) { g_simAlive = false; break; }
            TranslateMessage(&msg);
            DispatchMessage(&msg);
        }
        return g_simAlive && IsWindow(hwnd_);
    }

    void present() {
        if (!buf_) return;
        for (int y = 0; y < IMG_H; y++) {
            for (int x = 0; x < IMG_W; x++) {
                uint32_t px = lut_[lfb[y * IMG_W + x]];
                for (int sy = 0; sy < scale_; sy++) {
                    uint32_t *row = buf_ + (size_t)(y * scale_ + sy) * (size_t)w_
                                    + (size_t)x * scale_;
                    for (int sx = 0; sx < scale_; sx++) row[sx] = px;
                }
            }
        }
        HDC hdc = GetDC(hwnd_);
        HDC mem = CreateCompatibleDC(hdc);
        HBITMAP old = (HBITMAP)SelectObject(mem, bmp_);
        BitBlt(hdc, 0, 0, w_, h_, mem, 0, 0, SRCCOPY);
        SelectObject(mem, old);
        DeleteDC(mem);
        ReleaseDC(hwnd_, hdc);
        dirty_ = false;
    }

    bool dirty() const { return dirty_; }
    void markDirty() { dirty_ = true; }
    HWND id() const { return hwnd_; }

    ~Win32Window() {
        if (bmp_) DeleteObject(bmp_);
    }

private:
    HWND hwnd_ = nullptr;
    HBITMAP bmp_ = nullptr;
    uint32_t *buf_ = nullptr;
    int w_ = 0, h_ = 0, scale_ = 1;
    bool dirty_ = true;
    uint32_t lut_[65536];
};

#endif

// ---------------------------------------------------------------------------
// 脚本化确定性回放
// ---------------------------------------------------------------------------
struct Seg { uint32_t from, to; uint16_t btn; uint8_t dpad; };

// 进菜单：长按 S2 三秒（固件阈值 3000ms），然后下移、翻页
static const Seg DEMO_MENU[] = {
    // 开机动画期间固件会忽略输入（bootAnimActive 只更新基线），所以要等它放完。
    // setup() 自己吃掉 462ms，动画 3200ms -> 约 3662ms 结束，这里从 3700ms 开始按。
    { 3700,  6900, BTN_S2, 0 },       // 长按 S2 3.2s -> 进菜单（阈值 3000ms）
    { 6900,  7150, 0, 0 },            // 松开
    { 7150,  7350, 0, DP_RIGHT },     // -> 电池
    { 7350,  7700, 0, 0 },
    { 7700,  7900, 0, DP_RIGHT },     // -> 灯光
    { 7900,  8250, 0, 0 },
    { 8250,  8450, 0, DP_RIGHT },     // -> 背景
    { 8450,  8800, 0, 0 },
    { 8800,  9000, 0, DP_RIGHT },     // -> 休眠
    { 9000,  9350, 0, 0 },
    { 9350,  9550, 0, DP_RIGHT },     // -> 无线
    { 9550,  9900, 0, 0 },
    { 9900, 10100, 0, DP_LEFT },      // 回到休眠
    { 10100, 10450, 0, 0 },
    { 10450, 10650, BTN_A, 0 },       // A 进子页
    { 10650, 10950, 0, 0 },
    { 10950, 11200, 0, DP_DOWN },     // 下移两项
    { 11200, 11500, 0, 0 },
    { 11500, 11750, 0, DP_DOWN },
    { 11750, 12050, 0, 0 },
    { 12050, 12300, BTN_B, 0 },       // B 返回
    { 12300, 12700, 0, 0 },
};

// 巡演脚本（外部文本文件驱动，改截图表不用重编）
//   格式：
//     hold <from_ms> <to_ms> <key...>      key: up down left right a b s1 s2（可多个，'-' 表示无）
//     shot <文件名> <at_ms>                到点强制存一张 out/<文件名>.png
//     end  <ms>                            结束时间（省略则自动推算）
struct HoldSeg { uint32_t from, to; uint16_t btn; uint8_t dpad; };
struct Shot { std::string name; uint32_t at; bool done = false; };

struct Tour {
    std::vector<HoldSeg> holds;
    std::vector<Shot> shots;
    uint32_t endMs = 0;
};

static bool tourKey(const std::string &k, uint16_t &btn, uint8_t &dpad) {
    if (k == "-" || k == "none") return true;
    if (k == "up")    { dpad |= DP_UP;    return true; }
    if (k == "down")  { dpad |= DP_DOWN;  return true; }
    if (k == "left")  { dpad |= DP_LEFT;  return true; }
    if (k == "right") { dpad |= DP_RIGHT; return true; }
    if (k == "a")     { btn |= BTN_A;     return true; }
    if (k == "b")     { btn |= BTN_B;     return true; }
    if (k == "s1")    { btn |= BTN_S1;    return true; }
    if (k == "s2")    { btn |= BTN_S2;    return true; }
    return false;
}

static bool loadTour(const char *path, Tour &tour) {
    FILE *f = std::fopen(path, "r");
    if (!f) { std::fprintf(stderr, "[tour] 打不开脚本 %s\n", path); return false; }
    char line[512];
    int ln = 0;
    while (std::fgets(line, sizeof(line), f)) {
        ln++;
        char *hash = std::strchr(line, '#');
        if (hash) *hash = 0;
        std::vector<std::string> tk;
        for (char *p = std::strtok(line, " \t\r\n"); p; p = std::strtok(nullptr, " \t\r\n"))
            tk.push_back(p);
        if (tk.empty()) continue;
        if (tk[0] == "hold" && tk.size() >= 4) {
            HoldSeg h;
            h.from = (uint32_t)std::strtoul(tk[1].c_str(), nullptr, 10);
            h.to = (uint32_t)std::strtoul(tk[2].c_str(), nullptr, 10);
            h.btn = 0; h.dpad = 0;
            for (size_t i = 3; i < tk.size(); i++)
                if (!tourKey(tk[i], h.btn, h.dpad))
                    std::fprintf(stderr, "[tour] %d 行：不认识的键 '%s'\n", ln, tk[i].c_str());
            tour.holds.push_back(h);
        } else if (tk[0] == "shot" && tk.size() >= 3) {
            Shot s;
            s.name = tk[1];
            s.at = (uint32_t)std::strtoul(tk[2].c_str(), nullptr, 10);
            tour.shots.push_back(s);
        } else if (tk[0] == "end" && tk.size() >= 2) {
            tour.endMs = (uint32_t)std::strtoul(tk[1].c_str(), nullptr, 10);
        } else {
            std::fprintf(stderr, "[tour] %d 行：看不懂\n", ln);
        }
    }
    std::fclose(f);
    if (tour.endMs == 0) {
        uint32_t m = 0;
        for (auto &h : tour.holds) if (h.to > m) m = h.to;
        for (auto &s : tour.shots) if (s.at > m) m = s.at;
        tour.endMs = m + 500;
    }
    std::fprintf(stderr, "[tour] %zu 段按键, %zu 张截图, 到 %ums\n",
                 tour.holds.size(), tour.shots.size(), tour.endMs);
    return true;
}

static void tourInputAt(const Tour &tour, uint32_t ms, SimIn &in) {
    in.buttons = 0;
    in.dpad = 0;
    for (auto &h : tour.holds) {
        if (ms >= h.from && ms < h.to) { in.buttons = h.btn; in.dpad = h.dpad; return; }
    }
}

static void simInAt(const Seg *segs, int n, uint32_t ms, SimIn &in) {
    in.buttons = 0;
    in.dpad = 0;
    for (int i = 0; i < n; i++) {
        if (ms >= segs[i].from && ms < segs[i].to) {
            in.buttons = segs[i].btn;
            in.dpad = segs[i].dpad;
            return;
        }
    }
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------
static void usage() {
    std::fprintf(stderr,
        "用法:\n"
        "  sim --mode=keys   [--out=DIR] [--fps=30] [--tty-preview]\n"
        "      键盘实时操作：方向键=上下左右，1=S2，2=S1，z=A，x=B\n"
        "      （Win32 下读真实按下/松开，长按 S2 三秒可进菜单）\n"
        "  sim --mode=script [--out=DIR] [--demo=menu] [--step=5]\n"
        "      确定性回放，吐出 PNG 帧序列\n"
        "  sim --mode=idle   [--out=DIR] [--steps=400] [--step=16667]\n"
        "      只跑开机动画和主界面，用于冒烟测试\n");
}

#ifdef _WIN32
static LARGE_INTEGER g_qpcFreq, g_qpc0;
static void qpcStart() {
    QueryPerformanceFrequency(&g_qpcFreq);
    QueryPerformanceCounter(&g_qpc0);
}
static uint64_t qpcUs() {
    LARGE_INTEGER c;
    QueryPerformanceCounter(&c);
    return (uint64_t)(c.QuadPart - g_qpc0.QuadPart) * 1000000ULL / (uint64_t)g_qpcFreq.QuadPart;
}
#endif

#ifdef _WIN32
static LONG WINAPI simSeh(EXCEPTION_POINTERS *p) {
    EXCEPTION_RECORD *r = p->ExceptionRecord;
    HMODULE mod = nullptr;
    GetModuleHandleExA(GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                        (LPCSTR)r->ExceptionAddress, &mod);
    DWORD_PTR rva = mod ? ((DWORD_PTR)r->ExceptionAddress - (DWORD_PTR)mod) : 0;
    std::fprintf(stderr, "[seh] code=0x%08X addr=%p modRVA=0x%lx\n",
        (unsigned)r->ExceptionCode, (void *)r->ExceptionAddress, (unsigned long)rva);
    std::fflush(stderr);
    return EXCEPTION_CONTINUE_SEARCH;
}
#endif

int main(int argc, char **argv) {
#ifdef _WIN32
    SetUnhandledExceptionFilter(simSeh);
    ULONG_PTR gdiToken = 0;
    Gdiplus::GdiplusStartupInput gdiInput;
    Gdiplus::GdiplusStartup(&gdiToken, &gdiInput, nullptr);
#endif

    std::string mode = "keys", outdir = "out", demo = "menu";
    int fps = 30, steps = 400, stepUs = 16667;
    int scaleW = 3;
    bool ttyPreview = false, noWindow = false, dumpFrames = false;
    std::string scriptPath;
    int maxFrames = 60;

    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        auto val = [&](const char *k) -> const char * {
            size_t n = std::strlen(k);
            if (a.compare(0, n, k) == 0) return a.c_str() + n;
            return nullptr;
        };
        if (a == "--help" || a == "-h") { usage(); return 0; }
        else if (val("--mode=")) mode = val("--mode=");
        else if (val("--out=")) outdir = val("--out=");
        else if (val("--demo=")) demo = val("--demo=");
        else if (val("--fps=")) fps = std::atoi(val("--fps="));
        else if (val("--steps=")) steps = std::atoi(val("--steps="));
        else if (val("--step=")) stepUs = std::atoi(val("--step="));
        else if (a == "--tty-preview") ttyPreview = true;
        else if (val("--scale=")) scaleW = std::atoi(val("--scale="));
        else if (a == "--no-window") noWindow = true;
        else if (val("--script=")) scriptPath = val("--script=");
        else if (a == "--frames") dumpFrames = true;
        else if (val("--count=")) maxFrames = std::atoi(val("--count="));
        else if (val("--fs=")) g_fsRoot = val("--fs=");
    }
    if (!mkdirs(outdir)) { std::fprintf(stderr, "[sim] 建不了输出目录 %s\n", outdir.c_str()); return 1; }

    std::fprintf(stderr, "[sim] %dx%d mode=%s out=%s\n", IMG_W, IMG_H, mode.c_str(), outdir.c_str());
    setup();
    if (!lfbReady()) {
        std::fprintf(stderr, "[sim] lfb 没有分配成功（172x320 在 setup() 里从 PSRAM 分配）\n");
        return 1;
    }
    std::fprintf(stderr, "[sim] setup() 完成 t=%ums\n", (unsigned)millis());

    if (mode == "script") {
        const Seg *segs = DEMO_MENU;
        int nseg = (int)(sizeof(DEMO_MENU) / sizeof(DEMO_MENU[0]));
        uint32_t endMs = segs[nseg - 1].to + 200;
        const uint64_t base = g_us;   // setup() 已经用掉一段假时间，绝不能倒回 0
                                      // （倒回去会让开机动画的 t 变成巨大值，直接跳过动画）
        size_t idx = 0;
        uint64_t lastHash = 0;
        uint32_t fedMs = 0;
        for (uint32_t t = 0; t <= endMs; t += (uint32_t)stepUs / 1000 + 1) {
            g_us = base + (uint64_t)t * 1000ULL;
            SimIn in; simInAt(segs, nseg, t, in);
            feedInput(in.buttons, in.dpad);
            loop();
            uint64_t h = hashLfb();
            if (h != lastHash) {
                lastHash = h;
                char name[512];
                std::snprintf(name, sizeof(name), "%s/f%04zu_%06ums.png", outdir.c_str(), idx++, t);
                writePng(name);
            }
            fedMs = t;
        }
        std::fprintf(stderr, "[sim] script 完成：%zu 帧，%ums\n", idx, fedMs);
#ifdef _WIN32
        Gdiplus::GdiplusShutdown(gdiToken);
#endif
        return 0;
    }

    if (mode == "tour") {
        if (scriptPath.empty()) { std::fprintf(stderr, "[tour] 需要 --script=文件\n"); return 1; }
        Tour tour;
        if (!loadTour(scriptPath.c_str(), tour)) return 1;
        if (!mkdirs(outdir)) { std::fprintf(stderr, "[sim] 建不了输出目录 %s\n", outdir.c_str()); return 1; }

        // setup() 期间动画会忽略输入，所以脚本时间从 setup 之后开始算
        const uint64_t base = g_us;
        size_t done = 0;
        uint64_t lastHash = 0;
        uint32_t stepMs = (uint32_t)(stepUs / 1000);
        if (stepMs < 1) stepMs = 1;
        for (uint32_t t = 0; t <= tour.endMs; t += stepMs) {
            g_us = base + (uint64_t)t * 1000ULL;
            // 让 millis() 从真实时间轴开始（base 已含 setup 的耗时）
            // 先截图、再喂输入：截图时刻若正好是某次按键的起点，必须停在
            // "上一次动作已尘埃落定" 的画面上，否则每张图都会慢一拍、拍到下一个动作的结果。
            for (auto &s : tour.shots) {
                if (!s.done && t >= s.at) {
                    s.done = true;
                    std::string path = outdir + "/" + s.name + ".png";
                    if (!writePng(path))
                        std::fprintf(stderr, "[tour] 写失败 %s\n", path.c_str());
                    else
                        std::fprintf(stderr, "[tour] %-28s t=%ums\n", s.name.c_str(), t);
                    done++;
                }
            }
            SimIn in;
            tourInputAt(tour, t, in);
            feedInput(in.buttons, in.dpad);
            loop();
            uint64_t h = hashLfb();
            if (dumpFrames && h != lastHash) {
                lastHash = h;
                char nm[512];
                std::snprintf(nm, sizeof(nm), "%s/frame_%06ums.png", outdir.c_str(), t);
                writePng(nm);
            }
        }
        std::fprintf(stderr, "[tour] 完成：%zu 张截图\n", done);
#ifdef _WIN32
        Gdiplus::GdiplusShutdown(gdiToken);
#endif
        return 0;
    }

    if (mode == "wallpaper") {
        // 先跑过开机动画（这期间固件忽略输入，壁纸也还没开始动）
        for (int i = 0; i < 4000 && bootAnimActive; i++) { g_us += 5000; loop(); }
        g_us += 400000;            // 稳一下，让壁纸转起来
        loop();
        if (!mkdirs(outdir)) { std::fprintf(stderr, "[sim] 建不了输出目录 %s\n", outdir.c_str()); return 1; }

        uint64_t last = 0;
        int idx = 0;
        uint32_t t0 = millis();
        for (int step = 0; step < 60000 && idx < maxFrames; step++) {
            g_us += 5000;          // 5ms 一步，足够分辨
            loop();
            uint64_t h = hashLfb();
            if (h != last) {
                last = h;
                char nm[512];
                std::snprintf(nm, sizeof(nm), "%s/w%03d.png", outdir.c_str(), idx);
                if (!writePng(nm)) std::fprintf(stderr, "[wp] 写失败 %s\n", nm);
                std::fprintf(stderr, "[wp] w%03d  +%ums\n", idx, (unsigned)(millis() - t0));
                idx++;
            }
        }
        std::fprintf(stderr, "[wp] 共 %d 帧，跨度 %ums\n", idx, (unsigned)(millis() - t0));
#ifdef _WIN32
        Gdiplus::GdiplusShutdown(gdiToken);
#endif
        return 0;
    }

    if (mode == "idle") {
        size_t idx = 0;
        uint64_t lastHash = hashLfb();
        char name[512];
        std::snprintf(name, sizeof(name), "%s/f%04zu_boot.png", outdir.c_str(), idx++);
        writePng(name);
        for (int s = 0; s < steps; s++) {
            g_us += (uint64_t)stepUs;
            loop();
            uint64_t h = hashLfb();
            if (h != lastHash) {
                lastHash = h;
                std::snprintf(name, sizeof(name), "%s/f%04zu_%06ums.png", outdir.c_str(), idx++,
                              (unsigned)millis());
                writePng(name);
            }
        }
        std::fprintf(stderr, "[sim] idle 完成：%zu 帧\n", idx);
#ifdef _WIN32
        Gdiplus::GdiplusShutdown(gdiToken);
#endif
        return 0;
    }

    if (mode == "keys") {
#ifdef _WIN32
        WinKeys keys;
        bool haveKeys = keys.init();

        Win32Window win;
        const wchar_t *title = L"GP-Combine UI | Up/Down/Left/Right  1=S2  2=S1  z=A  x=B  Esc=quit";
        bool haveWin = !noWindow && win.open(scaleW, title);
        if (!haveWin) {
            std::fprintf(stderr, "[sim] 窗口打不开，退化为写 %s/preview.png\n", outdir.c_str());
        } else {
            std::fprintf(stderr, "[sim] 窗口已开 %dx%d（%d\u00d7\u653e\u5927）\n",
                         IMG_W * scaleW, IMG_H * scaleW, scaleW);
        }
        if (haveWin && haveKeys) keys.focusWindow(win.id());
        ConsoleKeys con;
        if (!haveWin) con.init();
        if (!haveKeys) {
            std::fprintf(stderr, "[sim] 警告：键盘读取不可用，按键不会有反应\n");
        }
        std::fprintf(stderr, "[sim] \u65b9\u5411\u952e=\u4e0a\u4e0b\u5de6\u53f3  1=S2  2=S1  z=A  x=B  Esc=\u9000\u51fa\n");

        qpcStart();
        uint64_t lastPreview = 0, lastHash = 0, lastPresent = 0;
        size_t saved = 0;
        const uint64_t previewUs = 1000000ULL / (uint64_t)(fps > 0 ? fps : 30);

        for (;;) {
            g_us = qpcUs();

            if (haveWin && !win.alive()) break;
            if (haveKeys && keys.quitRequested()) break;

            SimIn in;
            if (haveWin) keys.poll(in); else con.poll(in);
            feedInput(in.buttons, in.dpad);
            loop();

            uint64_t h = hashLfb();
            if (haveWin) {
                bool timeUp = g_us - lastPresent >= previewUs;
                if (h != lastHash || win.dirty() || timeUp) {
                    win.present();
                    lastPresent = g_us;
                    if (h != lastHash) { lastHash = h; saved++; }
                }
            } else if (g_us - lastPreview >= previewUs) {
                lastPreview = g_us;
                if (h != lastHash) {
                    lastHash = h;
                    writePng(outdir + "/preview.png");
                    saved++;
                }
            }
            Sleep(2);
        }
        if (haveWin) win.present();
        std::fprintf(stderr, "[sim] \u9000\u51fa\uff0c\u5171\u66f4\u65b0 %zu \u5e27\n", saved);
        Gdiplus::GdiplusShutdown(gdiToken);
        return 0;
#else
        // POSIX 分支保留原 X11 实现（本目录不编译）
        usage();
        return 1;
#endif
    }

    usage();
    return 1;
}
