// swift-tools-version: 5.9
import PackageDescription
let package = Package(
    name: "ATIVMac", platforms: [.macOS(.v13)],
    products: [.executable(name: "ATIV", targets: ["ATIV"])],
    targets: [
        .executableTarget(name: "ATIV", dependencies: ["SparkleBridge"], path: "Sources"),
        .target(name: "SparkleBridge", path: "SparkleBridge", publicHeadersPath: "include", linkerSettings: [.linkedFramework("Foundation")]),
        .testTarget(name: "ATIVTests", dependencies: ["ATIV"], path: "Tests")
    ]
)
