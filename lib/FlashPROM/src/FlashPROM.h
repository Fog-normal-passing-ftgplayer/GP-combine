/*
 * SPDX-License-Identifier: MIT
 * SPDX-FileCopyrightText: Copyright (c) 2021 Jason Skuby (mytechtoybox.com)
 */

#ifndef FLASHPROM_H_
#define FLASHPROM_H_

#include <stdint.h>
#include <string.h>
#include <pico/lock_core.h>
#include <pico/multicore.h>
#include <hardware/flash.h>
#include <hardware/timer.h>

#define EEPROM_SIZE_BYTES    0x8000           // Reserve 32k of flash memory (ensure this value is divisible by 256)
#define EEPROM_ADDRESS_START _u(0x101F8000) // The arduino-pico EEPROM lib starts here, so we'll do the same

// Warning: If the write wait is too long it can stall other processes
#define EEPROM_WRITE_WAIT    50             // Amount of time in ms to wait before blocking core1 and committing to flash

class FlashPROM
{
	public:
		void start();
		void commit();
		void reset();

		// 等待挂起的刷写真正落盘（最多 timeout_ms）。
		// 返回 true 表示已写完或本来就没有挂起；false 表示超时。
		// 需要“改完立刻重启”的场景必须用它，不能用固定 sleep 猜时间。
		bool waitCommit(uint32_t timeout_ms);

		static uint8_t writeCache[EEPROM_SIZE_BYTES];
};

inline FlashPROM EEPROM;

#endif
