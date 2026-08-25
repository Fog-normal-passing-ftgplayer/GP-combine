#pragma once

#include "GPGFX_UI_widgets.h"
#include "config.pb.h"

class LiteCustomLayoutScreen : public GPScreen {
  public:
    LiteCustomLayoutScreen() {}
    LiteCustomLayoutScreen(GPGFX* renderer) { setRenderer(renderer); }
    virtual ~LiteCustomLayoutScreen() {}
    virtual int8_t update();
    virtual void init();
    virtual void shutdown();
  protected:
    virtual void drawScreen();
};
