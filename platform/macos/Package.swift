// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "AVIDMac",
    platforms: [.macOS(.v12)],
    products: [.executable(name: "AVID", targets: ["AVID"])],
    targets: [.executableTarget(name: "AVID", path: "Sources")]
)
