// swift-tools-version: 6.3
import PackageDescription

// The UI remains a separate macOS 13 / Intel-compatible package. Only this
// optional process links the higher-deployment-target inference libraries.
let package = Package(
    name: "ATIVTranscriptionHelper",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "ATIVTranscriptionHelper", targets: ["ATIVTranscriptionHelper"])],
    dependencies: [
        .package(path: "../../build/transcription-core/apple/AVIDTranscription"),
        .package(path: "../../build/transcription-core/apple/AVIDTranscriptionEngines"),
    ],
    targets: [
        .target(name: "TranscriptionBridge", dependencies: [
            .product(name: "AVIDTranscription", package: "AVIDTranscription"),
        ]),
        .executableTarget(name: "ATIVTranscriptionHelper", dependencies: [
            "TranscriptionBridge",
            .product(name: "AVIDTranscription", package: "AVIDTranscription"),
            .product(name: "AVIDTranscriptionEngines", package: "AVIDTranscriptionEngines"),
        ]),
        .testTarget(name: "TranscriptionBridgeTests", dependencies: ["TranscriptionBridge"]),
    ]
)
