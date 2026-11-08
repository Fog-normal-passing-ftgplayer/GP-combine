/*
 * SPDX-License-Identifier: MIT
 * SPDX-FileCopyrightText: Copyright (c) 2021 Jason Skuby (mytechtoybox.com)
 */

#include "FlashPROM.h"
#include "pico/time.h"

uint8_t FlashPROM::writeCache[EEPROM_SIZE_BYTES];
volatile static alarm_id_t flashWriteAlarm = 0;
volatile static spin_lock_t *flashLock = nullptr;

int64_t writeToFlash(alarm_id_t id, void *flashCache)
{
	while (is_spin_locked(flashLock));

	// 开机早期（GP2040::setup() 里的 Storage::init()→ConfigUtils::load()→save()）就会
	// 安排一次刷写，而 core1 要到 main() 后半段才 multicore_launch_core1()。
	// 此时做 multicore_lockout 会**永久等待**（core1 没有 victim handler 应答，
	// 实测：调用后不再返回），表现为整机黑屏 + USB 不出现。
	// flash 擦写又必须锁住 core1，所以这里推迟重试，等 core1 就位再写。
	if (!multicore_lockout_victim_is_initialized(1)) {
		return (int64_t)EEPROM_WRITE_WAIT * 1000; // µs：过 50ms 再试
	}

	multicore_lockout_start_blocking();
	uint32_t interrupts = spin_lock_blocking(flashLock);

	flash_range_erase((intptr_t)EEPROM_ADDRESS_START - (intptr_t)XIP_BASE, EEPROM_SIZE_BYTES);
	flash_range_program((intptr_t)EEPROM_ADDRESS_START - (intptr_t)XIP_BASE, reinterpret_cast<uint8_t *>(flashCache), EEPROM_SIZE_BYTES);

	flashWriteAlarm = 0;

	multicore_lockout_end_blocking();
	spin_unlock(flashLock, interrupts);

	return 0;
}

void FlashPROM::start()
{
	if (flashLock == nullptr)
		flashLock = spin_lock_instance(spin_lock_claim_unused(true));

	memcpy(writeCache, reinterpret_cast<uint8_t *>(EEPROM_ADDRESS_START), EEPROM_SIZE_BYTES);
}

/* We don't have an actual EEPROM, so we need to be extra careful about minimizing writes. Instead
	of writing when a commit is requested, we update a time to actually commit. That way, if we receive multiple requests
	to commit in that timeframe, we'll hold off until the user is done sending changes. */
void FlashPROM::commit()
{
	while (is_spin_locked(flashLock));
	if (flashWriteAlarm != 0)
		cancel_alarm(flashWriteAlarm);
	flashWriteAlarm = add_alarm_in_ms(EEPROM_WRITE_WAIT, writeToFlash, writeCache, true);
}

bool FlashPROM::waitCommit(uint32_t timeout_ms)
{
	// writeToFlash() 在 flash_range_program() 之后把 flashWriteAlarm 清零，
	// 所以它归零就代表数据已经写进 flash（而不是“还在排队的 50ms 等待”）。
	// 注意：这里在链路 addon 的主循环上下文里轮询，不能用 multicore_lockout，
	// 刷写本身由 alarm 中断完成。
	absolute_time_t deadline = make_timeout_time_ms(timeout_ms);
	while (flashWriteAlarm != 0 && !time_reached(deadline)) {
		sleep_ms(1);
	}
	return flashWriteAlarm == 0;
}

void FlashPROM::reset()
{
	memset(writeCache, 0, EEPROM_SIZE_BYTES);
	commit();
}
