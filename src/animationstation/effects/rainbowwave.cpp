#include "rainbowwave.h"
#include "storagemanager.h"

RainbowWave::RainbowWave(PixelMatrix &matrix) : Animation(matrix) {
  // spread the full rainbow across the strip
  int maxPos = 0;
  for (auto &col : matrix.pixels)
    for (auto &pixel : col)
      for (auto &pos : pixel.positions)
        if ((int)pos > maxPos) maxPos = pos;
  if (maxPos > 0) hueStep = (uint8_t)(255 / (maxPos + 1));
}

bool RainbowWave::Animate(RGB (&frame)[100]) {
  if (!time_reached(this->nextRunTime)) {
    return false;
  }

  UpdateTime();
  UpdatePresses(frame);

  for (auto &col : matrix->pixels) {
    for (auto &pixel : col) {
      if (pixel.index == NO_PIXEL.index)
        continue;

      DecrementFadeCounter(pixel.index);

      for (auto &pos : pixel.positions) {
        uint8_t hue = (uint8_t)(this->currentFrame + pos * this->hueStep);
        RGB color = RGB::wheel(hue);
        frame[pos] = BlendColor(hitColor[pixel.index], color, times[pixel.index]);
      }
    }
  }

  this->currentFrame++;

  AnimationOptions & animationOptions = Storage::getInstance().getAnimationOptions();
  this->nextRunTime = make_timeout_time_ms(animationOptions.flowCycleTime);

  return true;
}

#define RAINBOW_CYCLE_INCREMENT   10
#define RAINBOW_CYCLE_MAX         INT16_MAX - RAINBOW_CYCLE_INCREMENT
#define RAINBOW_CYCLE_MIN         1         + RAINBOW_CYCLE_INCREMENT

void RainbowWave::ParameterUp() {
  AnimationOptions & animationOptions = Storage::getInstance().getAnimationOptions();
  if (animationOptions.flowCycleTime < RAINBOW_CYCLE_MAX) {
    animationOptions.flowCycleTime = animationOptions.flowCycleTime + RAINBOW_CYCLE_INCREMENT;
  } else {
    animationOptions.flowCycleTime = INT16_MAX;
  }
}

void RainbowWave::ParameterDown() {
  AnimationOptions & animationOptions = Storage::getInstance().getAnimationOptions();
  if (animationOptions.flowCycleTime > RAINBOW_CYCLE_MIN) {
    animationOptions.flowCycleTime = animationOptions.flowCycleTime - RAINBOW_CYCLE_INCREMENT;
  } else {
    animationOptions.flowCycleTime = 1;
  }
}
