#ifndef SparkleBridge_h
#define SparkleBridge_h

#include <stdbool.h>

void ATIVSetUpdateWorkInProgress(bool working);
bool ATIVStartUpdater(void);
bool ATIVCheckForUpdates(void);
// Route the native menu action to a Sparkle-compatible controller.
bool ATIVCheckForUpdatesWithController(void *controller);

#endif
