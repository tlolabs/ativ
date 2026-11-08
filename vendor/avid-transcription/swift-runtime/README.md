# Swift compatibility runtime

The helper packager uses Apple's `swift-stdlib-tool` to identify required Swift
compatibility libraries, includes them in the nested helper's `Contents/Frameworks`, thins them to arm64,
and signs them before signing the containing application. It removes developer
search paths and retains local runtime discovery. The package integrity manifest
records the exact bytes shipped with each build.

`LICENSE.txt` is the official Apache 2.0 license with Swift Runtime Library
Exception from the Swift 6.4.2 release used for the initial native verification:
https://raw.githubusercontent.com/swiftlang/swift/swift-6.4.2-RELEASE/LICENSE.txt

Copyright Apple Inc. and the Swift project authors. This notice and license are
distributed with the helper in addition to the separate model and SDK notices.
