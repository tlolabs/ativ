#import "SparkleBridge.h"

#import <Foundation/Foundation.h>
#import <objc/message.h>
#import <objc/runtime.h>

static id ATIVUpdaterController;
static BOOL ATIVWorkInProgress;

// Sparkle is loaded dynamically; these selectors follow SPUUpdaterDelegate.
@interface ATIVUpdateDelegate : NSObject
@end
@implementation ATIVUpdateDelegate
- (BOOL)updater:(id)updater mayPerformUpdateCheck:(NSInteger)check error:(NSError **)error {
    if (ATIVWorkInProgress && error) *error = [NSError errorWithDomain:@"com.tlolabs.ativ.updates" code:1 userInfo:@{NSLocalizedDescriptionKey:@"Finish the current export before updating."}];
    return !ATIVWorkInProgress;
}
- (BOOL)updater:(id)updater shouldProceedWithUpdate:(id)item updateCheck:(NSInteger)check error:(NSError **)error {
    return [self updater:updater mayPerformUpdateCheck:check error:error];
}
- (NSArray *)allowedSystemProfileKeysForUpdater:(id)updater { return @[]; }
- (BOOL)updater:(id)updater shouldPostponeRelaunchForUpdate:(id)item untilInvokingBlock:(void (^)(void))installHandler {
    if (!ATIVWorkInProgress) return NO;
    [NSTimer scheduledTimerWithTimeInterval:1.0 repeats:YES block:^(NSTimer *timer) {
        if (!ATIVWorkInProgress) { [timer invalidate]; installHandler(); }
    }];
    return YES;
}
@end
static ATIVUpdateDelegate *ATIVUpdaterDelegate;
void ATIVSetUpdateWorkInProgress(bool working) { ATIVWorkInProgress = working; }


bool ATIVStartUpdater(void) {
    if (ATIVUpdaterController != nil) {
        return true;
    }

    NSString *key = [NSBundle.mainBundle objectForInfoDictionaryKey:@"SUPublicEDKey"];
    if (key == nil || [[NSData alloc] initWithBase64EncodedString:key options:0].length != 32) return false;
    NSString *frameworkPath = [NSBundle.mainBundle.privateFrameworksPath
        stringByAppendingPathComponent:@"Sparkle.framework"];
    NSBundle *framework = [NSBundle bundleWithPath:frameworkPath];
    if (framework == nil || ![framework load]) {
        return false;
    }

    Class controllerClass = NSClassFromString(@"SPUStandardUpdaterController");
    SEL initializer = NSSelectorFromString(
        @"initWithStartingUpdater:updaterDelegate:userDriverDelegate:"
    );
    if (controllerClass == Nil || ![controllerClass instancesRespondToSelector:initializer]) {
        return false;
    }

    ATIVUpdaterDelegate = [ATIVUpdateDelegate new];
    id allocated = ((id (*)(id, SEL))objc_msgSend)(controllerClass, sel_registerName("alloc"));
    ATIVUpdaterController = ((id (*)(id, SEL, BOOL, id, id))objc_msgSend)(
        allocated,
        initializer,
        YES,
        ATIVUpdaterDelegate,
        nil
    );
    return ATIVUpdaterController != nil;
}

bool ATIVCheckForUpdates(void) {
    if (!ATIVStartUpdater()) {
        return false;
    }

    SEL updaterSelector = NSSelectorFromString(@"updater");
    id updater = ((id (*)(id, SEL))objc_msgSend)(ATIVUpdaterController, updaterSelector);
    SEL checkSelector = NSSelectorFromString(@"checkForUpdates:");
    if (updater == nil || ![updater respondsToSelector:checkSelector]) {
        return false;
    }
    ((void (*)(id, SEL, id))objc_msgSend)(updater, checkSelector, nil);
    return true;
}
