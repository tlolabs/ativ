#ifndef SparkleBridge_h
#define SparkleBridge_h

#include <stdbool.h>

void ATIVSetUpdateWorkInProgress(bool working);
bool ATIVStartUpdater(void);
bool ATIVCheckForUpdates(void);

#endif
