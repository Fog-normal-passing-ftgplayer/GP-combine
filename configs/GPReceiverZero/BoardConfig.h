/*
 * SPDX-License-Identifier: MIT
 * SPDX-FileCopyrightText: Copyright (c) 2026 GP-Fusion
 */

#ifndef GPRECEIVERZERO_BOARD_CONFIG_H_
#define GPRECEIVERZERO_BOARD_CONFIG_H_

#include "enums.pb.h"
#include "class/hid/hid.h"

#define BOARD_CONFIG_LABEL "GPReceiverZero"

// No buttons on the receiver: all input comes from the nRF24 link.

// Keyboard Mapping Configuration (so keyboard input mode works too)
#define KEY_DPAD_UP     HID_KEY_ARROW_UP
#define KEY_DPAD_DOWN   HID_KEY_ARROW_DOWN
#define KEY_DPAD_RIGHT  HID_KEY_ARROW_RIGHT
#define KEY_DPAD_LEFT   HID_KEY_ARROW_LEFT
#define KEY_BUTTON_B1   HID_KEY_SHIFT_LEFT
#define KEY_BUTTON_B2   HID_KEY_Z
#define KEY_BUTTON_R2   HID_KEY_X
#define KEY_BUTTON_L2   HID_KEY_V
#define KEY_BUTTON_B3   HID_KEY_CONTROL_LEFT
#define KEY_BUTTON_B4   HID_KEY_ALT_LEFT
#define KEY_BUTTON_R1   HID_KEY_SPACE
#define KEY_BUTTON_L1   HID_KEY_C
#define KEY_BUTTON_S1   HID_KEY_5
#define KEY_BUTTON_S2   HID_KEY_1
#define KEY_BUTTON_L3   HID_KEY_EQUAL
#define KEY_BUTTON_R3   HID_KEY_MINUS
#define KEY_BUTTON_A1   HID_KEY_9
#define KEY_BUTTON_A2   HID_KEY_F2
#define KEY_BUTTON_FN   -1

// nRF24L01 wireless receiver (SPI0), 与 GPReceiver 相同的引脚
#define WIRELESS_RECEIVER_ENABLED 1
#define WIRELESS_RX_CE_PIN   6
#define WIRELESS_RX_CSN_PIN  5
#define WIRELESS_RX_SCK_PIN  2
#define WIRELESS_RX_MOSI_PIN 3
#define WIRELESS_RX_MISO_PIN 4
#define WIRELESS_RX_LED_PIN  -1   // 不用普通指示灯
#define WIRELESS_RX_RGB_LED_PIN 16 // RP2040-Zero 板载 WS2812

// no LED strip on the receiver
#define BOARD_LEDS_PIN -1

#endif
