// 宿主机 UI 仿真用的最小 Arduino 垫片。
// 只提供“平台 API”，绝不放任何 UI 业务逻辑 —— 一旦往这里抄业务逻辑，
// 截出来的图就证明不了真机行为了（nRF24 那个 bug 就是这么来的）。
#pragma once

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <cstdarg>
#include <cmath>
#include <string>
#include <dirent.h>
#include <sys/stat.h>
#include <strings.h>

// ---------------- 常量 ----------------
#define HIGH 0x1
#define LOW  0x0
#define INPUT        0x01
#define OUTPUT       0x03
#define INPUT_PULLUP 0x05

#define SERIAL_8N1 0x800001c

// ESP32 的 SPI 总线编号
#define FSPI 0
#define HSPI 1
#define VSPI 2

#define LED_BUILTIN 2

// ESP32 上 PROGMEM 是"放 flash"的提示；宿主机上不需要
#ifndef PROGMEM
#define PROGMEM
#endif

// ESP32 Arduino 的 loop 任务栈设置宏，宿主机上无事可做
#ifndef SET_LOOP_TASK_STACK_SIZE
#define SET_LOOP_TASK_STACK_SIZE(x)
#endif

// ---------------- 数学 ----------------
#define constrain(amt, low, high) ((amt) < (low) ? (low) : ((amt) > (high) ? (high) : (amt)))

// ---------------- PSRAM ----------------
// ESP32 上分到 PSRAM；宿主机上就是普通堆
static inline void *ps_malloc(size_t n) { return std::malloc(n); }
static inline void *ps_calloc(size_t n, size_t s) { return std::calloc(n, s); }
static inline void *ps_realloc(void *p, size_t n) { return std::realloc(p, n); }

// ---------------- String ----------------
// 只实现固件实际用到的成员，够用即可。
class String {
public:
    String() {}
    String(const char *s) : s_(s ? s : "") {}
    String(const std::string &s) : s_(s) {}
    String &operator=(const char *s) { s_ = s ? s : ""; return *this; }

    const char *c_str() const { return s_.c_str(); }
    size_t length() const { return s_.size(); }

    void trim() {
        size_t b = s_.find_first_not_of(" \t\r\n");
        if (b == std::string::npos) { s_.clear(); return; }
        size_t e = s_.find_last_not_of(" \t\r\n");
        s_ = s_.substr(b, e - b + 1);
    }

    int indexOf(char c) const {
        size_t p = s_.find(c);
        return p == std::string::npos ? -1 : (int)p;
    }
    int indexOf(const char *needle) const {
        size_t p = s_.find(needle);
        return p == std::string::npos ? -1 : (int)p;
    }

    String substring(int from) const {
        if (from < 0 || (size_t)from > s_.size()) return String();
        return String(s_.substr((size_t)from));
    }
    String substring(int from, int to) const {
        if (from < 0) from = 0;
        if ((size_t)from > s_.size()) return String();
        if (to < from) to = from;
        if ((size_t)to > s_.size()) to = (int)s_.size();
        return String(s_.substr((size_t)from, (size_t)(to - from)));
    }

    long toInt() const { return std::strtol(s_.c_str(), nullptr, 10); }

    bool operator==(const char *o) const { return s_ == (o ? o : ""); }
    bool operator==(const String &o) const { return s_ == o.s_; }
    bool operator!=(const char *o) const { return !(*this == o); }

private:
    std::string s_;
};

// ---------------- File / LittleFS ----------------
// 仿真时把根目录指向本地一个目录，读不到就反馈“不存在”，固件会自己走默认值。
class File {
public:
    File() {}
    explicit File(FILE *fp) : fp_(fp) {}
    File(DIR *d, const std::string &path) : dir_(d), path_(path) {}

    operator bool() const { return fp_ != nullptr || dir_ != nullptr; }

    bool isDirectory() const { return dir_ != nullptr; }
    const char *name() const { return name_.c_str(); }

    // 目录遍历（NES 的 ROM 列表要用）
    File openNextFile() {
        if (!dir_) return File();
        struct dirent *e;
        while ((e = ::readdir(dir_)) != nullptr) {
            std::string n = e->d_name;
            if (n == "." || n == "..") continue;
            std::string child = path_ + "/" + n;
            struct stat st;
            if (::stat(child.c_str(), &st) == 0 && S_ISDIR(st.st_mode)) {
                DIR *d = ::opendir(child.c_str());
                if (!d) return File();
                File f(d, child);
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

    int available() {
        if (!fp_) return 0;
        long cur = std::ftell(fp_);
        std::fseek(fp_, 0, SEEK_END);
        long end = std::ftell(fp_);
        std::fseek(fp_, cur, SEEK_SET);
        return (int)(end - cur);
    }

    int read() { return fp_ ? std::fgetc(fp_) : -1; }
    size_t read(uint8_t *buf, size_t len) { return fp_ ? std::fread(buf, 1, len, fp_) : 0; }

    String readStringUntil(char delim) {
        std::string out;
        if (!fp_) return String();
        int c;
        while ((c = std::fgetc(fp_)) != EOF) {
            if ((char)c == delim) break;
            out.push_back((char)c);
        }
        return String(out);
    }

    size_t size() {
        if (!fp_) return 0;
        long cur = std::ftell(fp_);
        std::fseek(fp_, 0, SEEK_END);
        long end = std::ftell(fp_);
        std::fseek(fp_, cur, SEEK_SET);
        return end < 0 ? 0 : (size_t)end;
    }

    int printf(const char *fmt, ...) {
        if (!fp_) return 0;
        va_list ap;
        va_start(ap, fmt);
        int n = std::vfprintf(fp_, fmt, ap);
        va_end(ap);
        return n;
    }

    void flush() { if (fp_) std::fflush(fp_); }

    void close() {
        if (fp_) { std::fclose(fp_); fp_ = nullptr; }
        if (dir_) { ::closedir(dir_); dir_ = nullptr; }
    }

private:
    FILE *fp_ = nullptr;
    DIR *dir_ = nullptr;
    std::string path_;
    std::string name_;
};

class SimLittleFS {
public:
    bool begin(bool /*formatOnFail*/ = false) { return true; }
    bool exists(const char *path);
    File open(const char *path, const char *mode = "r");
};

extern SimLittleFS LittleFS;

// ---------------- Serial ----------------
class SimSerial {
public:
    void begin(uint32_t /*baud*/, uint32_t /*config*/ = SERIAL_8N1, int8_t /*rx*/ = -1, int8_t /*tx*/ = -1) {}
    size_t write(const uint8_t * /*buf*/, size_t len) { return len; }
    size_t write(uint8_t b) { (void)b; return 1; }
    int available() { return 0; }
    int read() { return -1; }
    void onReceive(void (*)(void)) {}
    int printf(const char *fmt, ...) {
        va_list ap;
        va_start(ap, fmt);
        int n = std::vfprintf(stderr, fmt, ap);
        va_end(ap);
        return n;
    }
};

extern SimSerial Serial;

// ---------------- 平台函数（在 sim_main.cpp 里定义） ----------------
uint32_t millis();
uint32_t micros();
void delay(uint32_t ms);
void delayMicroseconds(uint32_t us);

void pinMode(uint8_t pin, uint8_t mode);
void digitalWrite(uint8_t pin, uint8_t val);
int digitalRead(uint8_t pin);

bool ledcAttach(uint8_t pin, uint32_t freq, uint8_t resolution);
bool ledcWrite(uint8_t pin, uint32_t duty);

// 仿真里没有引脚，ADC 一律返回中点
uint16_t analogRead(uint8_t pin);
