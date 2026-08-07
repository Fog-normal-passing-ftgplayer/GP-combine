#pragma once

#include "GPGFX_UI_widgets.h"
#include "config.pb.h"

class GPFusionMenuScreen : public GPScreen {
  public:
    GPFusionMenuScreen() {}
    GPFusionMenuScreen(GPGFX* renderer) { setRenderer(renderer); }
    virtual ~GPFusionMenuScreen() {}
    virtual int8_t update();
    virtual void init();
    virtual void shutdown();
  protected:
    virtual void drawScreen();
};
