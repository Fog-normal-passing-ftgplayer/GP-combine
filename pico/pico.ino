// GP-Fusion: Pico gamepad-style input over UART
// UART0 (Serial1): TX=GPIO0, RX=GPIO1 @ 921600 8N1
// Button pins follow GP2040-CE Pico board config:
//   DPAD_LEFT = GPIO5, DPAD_RIGHT = GPIO4, B1(A) = GPIO6, B2(B) = GPIO7
// INPUT frame payload = buttons(16bit) + dpad(8bit), GP2040-CE bit layout
// Onboard LED (GPIO25) toggles on each valid ACK frame from ESP32

#define PIN_LEFT      5
#define PIN_RIGHT     4
#define PIN_A         6
#define PIN_B         7
#define LED_PIN       25
#define UART_BAUD     921600
#define HEARTBEAT_MS  50
#define DEBOUNCE_MS   5

#define FRAME_MAGIC      0xAA
#define FRAME_VERSION    1
#define FRAME_TYPE_INPUT 0x01
#define FRAME_TYPE_ACK   0x02

// GP2040-CE masks (GamepadState.h)
#define MASK_B1      0x0001
#define MASK_B2      0x0002
#define MASK_DPAD_L  0x04
#define MASK_DPAD_R  0x08

// CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF)
static uint16_t crc16_update(uint16_t crc, uint8_t b) {
  crc ^= (uint16_t)b << 8;
  for (int i = 0; i < 8; i++) {
    crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
  }
  return crc;
}

// combined 8-bit state: bit0=B1, bit1=B2, bit2=LEFT, bit3=RIGHT
uint8_t readState() {
  uint8_t s = 0;
  if (digitalRead(PIN_A) == LOW)    s |= MASK_B1;
  if (digitalRead(PIN_B) == LOW)    s |= MASK_B2;
  if (digitalRead(PIN_LEFT) == LOW) s |= MASK_DPAD_L;
  if (digitalRead(PIN_RIGHT) == LOW)s |= MASK_DPAD_R;
  return s;
}

// debounce / send state
uint8_t lastRawState = 0;
uint8_t acceptedState = 0;
uint8_t lastSentState = 0;
uint32_t changeTime = 0;
uint32_t lastSent = 0;

// RX state machine
uint8_t rxState = 0; // 0 idle, 1 ver, 2 type, 3 len, 4 payload, 5 crcLo, 6 crcHi
uint8_t rxType = 0;
uint8_t rxLen = 0;
uint8_t rxIdx = 0;
uint8_t rxPayload[16];
uint16_t rxCrcCalc = 0;
uint8_t rxCrcLo = 0;

void sendInputFrame(uint8_t state) {
  uint8_t buttons = state & 0x03; // B1 | B2
  uint8_t dpad = state & 0x0C;    // LEFT | RIGHT
  uint8_t frame[9];
  frame[0] = FRAME_MAGIC;
  frame[1] = FRAME_VERSION;
  frame[2] = FRAME_TYPE_INPUT;
  frame[3] = 3; // payload: buttons_lo, buttons_hi, dpad
  frame[4] = buttons;
  frame[5] = 0;
  frame[6] = dpad;
  uint16_t crc = 0xFFFF;
  for (int i = 1; i <= 6; i++) crc = crc16_update(crc, frame[i]);
  frame[7] = (uint8_t)(crc & 0xFF);
  frame[8] = (uint8_t)(crc >> 8);
  Serial1.write(frame, sizeof(frame));
}

void handleRxByte(uint8_t b) {
  switch (rxState) {
    case 0:
      if (b == FRAME_MAGIC) rxState = 1;
      break;
    case 1:
      rxCrcCalc = 0xFFFF;
      rxCrcCalc = crc16_update(rxCrcCalc, b);
      rxState = (b == FRAME_VERSION) ? 2 : 0;
      break;
    case 2:
      rxType = b;
      rxCrcCalc = crc16_update(rxCrcCalc, b);
      rxState = 3;
      break;
    case 3:
      rxLen = b;
      rxCrcCalc = crc16_update(rxCrcCalc, b);
      if (rxLen > sizeof(rxPayload)) { rxState = 0; break; }
      rxIdx = 0;
      rxState = (rxLen == 0) ? 5 : 4;
      break;
    case 4:
      rxPayload[rxIdx++] = b;
      rxCrcCalc = crc16_update(rxCrcCalc, b);
      if (rxIdx == rxLen) rxState = 5;
      break;
    case 5:
      rxCrcLo = b;
      rxState = 6;
      break;
    case 6:
      if (b == (uint8_t)(rxCrcCalc >> 8) &&
          rxCrcLo == (uint8_t)(rxCrcCalc & 0xFF) &&
          rxType == FRAME_TYPE_ACK) {
        digitalWrite(LED_PIN, !digitalRead(LED_PIN));
      }
      rxState = 0;
      break;
  }
}

void setup() {
  Serial1.begin(UART_BAUD);
  pinMode(PIN_LEFT, INPUT_PULLUP);
  pinMode(PIN_RIGHT, INPUT_PULLUP);
  pinMode(PIN_A, INPUT_PULLUP);
  pinMode(PIN_B, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
}

void loop() {
  uint32_t now = millis();

  // debounce combined state
  uint8_t raw = readState();
  if (raw != lastRawState) {
    lastRawState = raw;
    changeTime = now;
  }
  if (raw != acceptedState && now - changeTime >= DEBOUNCE_MS) {
    acceptedState = raw;
  }

  // send on change, plus heartbeat
  if (acceptedState != lastSentState || now - lastSent >= HEARTBEAT_MS) {
    lastSentState = acceptedState;
    lastSent = now;
    sendInputFrame(acceptedState);
  }

  while (Serial1.available()) {
    handleRxByte((uint8_t)Serial1.read());
  }
}
