#pragma once
// 手机 App 的 BLE 控制面：NUS（Nordic UART）风格 GATT，里面跑 proto.h 那套帧。
// 用 NUS 的 UUID 是为了 P1 阶段能直接拿手机上的 nRF Connect 手敲帧验证，
// 不用等 App 写完（见 docs/superpowers/specs/2026-09-18-phone-app-design.md §3）。
//
// 用法（都在主循环/菜单上下文里调，回调里的活只做入队）：
//   bleLinkBegin(name)  装协议栈并建 GATT —— 第一次开蓝牙时才调，不占用默认内存
//   bleLinkEnable(on)   开/关广播（对应菜单「蓝牙」页那个开关）
//   bleLinkTick()       推进发送队列
//   bleLinkPollRx(f)    取一帧（收到才返回 true）
//   bleLinkSend(...)    发一帧（内部按 MTU 分片，由 bleLinkTick 慢慢吐）

#include <stdint.h>
#include <stddef.h>
#include "proto.h"

// BLE 一次 notify 最多能带 MTU-3 字节（3 字节是 ATT 头）。
// 单独抽成 inline 是为了能在主机上测：这个数算错（用期望 MTU 而不是协商后的 MTU）
// 的后果是 notify 一直失败 → txOff 不前进 → 回包永久卡死。
// mtu 传 0（还没连上/未知）时退到 BLE 的最小 MTU 23。
static inline size_t bleNotifyChunk(uint16_t mtu, size_t remaining) {
  size_t m = (mtu > 3) ? (size_t)(mtu - 3) : 20u;
  return remaining < m ? remaining : m;
}

// 装协议栈 + 建服务。deviceName 太长会被截断成 15 字节。返回 false = 内存不够/失败
bool bleLinkBegin(const char *deviceName);

// 开关广播。关的时候顺便断开已连接的手机（菜单里关开关就是要它停）
void bleLinkEnable(bool on);

// 主循环调用：推进 TX 分片
void bleLinkTick(void);

// 主循环调用：取一帧（没有就返回 false）
bool bleLinkPollRx(ProtoFrame &out);

// 发一帧（真正发出去在 bleLinkTick 里，按 MTU 分片）。返回 false = 没连接或载荷超限
bool bleLinkSend(uint8_t cmd, uint16_t seq, const uint8_t *payload, uint16_t len);

// 0=未启用 1=广播中 2=已连接（菜单「蓝牙」页直接显示这个）
int bleLinkState(void);

// 已连接手机数
int bleLinkClients(void);

// 协议栈此刻到底在不在广播（区别于"开关是开的"）——调试/菜单显示用
bool bleLinkAdvertising(void);

// 协议栈是否已装（装过就一直占着内存，关开关只是停广播）
bool bleLinkInited(void);

// 当前连接是否已通过 AUTH（配对码校验）；断连自动清零
bool bleLinkAuthed(void);
void bleLinkSetAuthed(bool v);

// 断开所有已连接手机（「清除配对」/关开关时用）
void bleLinkDisconnectAll(void);

// 断开 + 撤销认证 + 丢掉半帧/残帧。换配对码、关开关这类「这次会话作废」的动作都要走它，
// 否则已经通过 AUTH 的手机在换码之后仍然是 authed=true，还能继续读改设置。
void bleLinkClearSession(void);
