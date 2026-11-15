#pragma once
// NES ROM 路径拼接。
// 为什么单独抽一个头文件：
//   1) 这个坑踩过两次 —— 先是用 28 字节存文件名、后是用 80 字节局部缓冲拼路径，
//      两次的症状都一样：open 不存在的路径 → 用户看到「按 A 启动游戏没反应」。
//      上限集中写在这里，改了名字长度就会编译期/测试期被抓住。
//   2) 主机侧回归测试要 include 固件真正用的这份实现，而不是另写一遍
//      （另写一遍的测试救不了真代码，上个花屏 bug 就是这么漏过去的）。
#include <stdio.h>
#include <stddef.h>

// 卡里文件名的最大长度（含结尾 0，即最多 95 个字符）——和主固件里 nesNames 的列宽一致
#define NES_ROM_NAME_MAX 96
// "/nes/" + 名字 + 结尾 0，再留点余量
#define NES_ROM_PATH_MAX (NES_ROM_NAME_MAX + 16)

// 返回 snprintf 的返回值：>= cap 就说明被截断了，调用方可以直接据此报错/打日志。
static inline int nesBuildRomPath(char *out, size_t cap, const char *name) {
  return snprintf(out, cap, "/nes/%s", name);
}
