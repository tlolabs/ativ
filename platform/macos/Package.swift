// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ATIVMac",
    platforms: [.macOS(.v12)],
    products: [.executable(name: "ATIV", targets: ["ATIV"])],
    targets: [.executableTarget(name: "ATIV", path: "Sources")]
)
