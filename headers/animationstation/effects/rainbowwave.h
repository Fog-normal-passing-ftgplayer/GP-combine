#ifndef _RAINBOWWAVE_H_
#define _RAINBOWWAVE_H_

#include "animation.h"
#include "hardware/clocks.h"
#include <stdio.h>
#include <stdlib.h>
#include <vector>
#include "animationstation.h"

// Rainbow gradient flowing along the strip (base animation index 5)
#define ANIM_RAINBOW_WAVE 5

class RainbowWave : public Animation {
public:
  RainbowWave(PixelMatrix &matrix);
  ~RainbowWave() {};

  bool Animate(RGB (&frame)[100]);
  void ParameterUp();
  void ParameterDown();

protected:
  int currentFrame = 0;
  uint8_t hueStep = 16; // rainbow spread across the strip
  absolute_time_t nextRunTime = nil_time;
};

#endif
