#import "SparkleBridge.h"

#import <Foundation/Foundation.h>
#import <objc/message.h>
#import <objc/runtime.h>

static id ATIVUpdaterController;

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

    id allocated = ((id (*)(id, SEL))objc_msgSend)(controllerClass, sel_registerName("alloc"));
    ATIVUpdaterController = ((id (*)(id, SEL, BOOL, id, id))objc_msgSend)(
        allocated,
        initializer,
        YES,
        nil,
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
