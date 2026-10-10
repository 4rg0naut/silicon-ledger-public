// swift-tools-version: 6.0
// granite-runner — gate + benchmark the Granite-Embedding-97M Core AI bundle.
//
// Depends on the locally checked-out coreai-kit at tag 0.4.2 (the release validated
// against Xcode 27 / macOS 27), not on a fresh fetch, so the run is reproducible.
import PackageDescription

let package = Package(
    name: "granite-runner",
    platforms: [.macOS("27.0")],
    dependencies: [
        .package(path: "../../repos/coreai-kit"),
    ],
    targets: [
        .executableTarget(
            name: "granite-runner",
            dependencies: [
                .product(name: "CoreAIKitVision", package: "coreai-kit"),
            ]
        ),
    ]
)
