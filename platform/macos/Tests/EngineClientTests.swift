import AppKit
import XCTest
import SparkleBridge
@testable import ATIV

final class EngineClientTests: XCTestCase {
    func testRealEnginePresets() throws {
        guard ProcessInfo.processInfo.environment["ATIV_ENGINE_PATH"] != nil else {
            throw XCTSkip("Set ATIV_ENGINE_PATH to test the native process boundary")
        }
        let done = expectation(description: "presets")
        EngineClient().fetchPresets { result in
            switch result {
            case .success(let presets):
                XCTAssertEqual(presets.count, 27)
                XCTAssertTrue(presets.allSatisfy { $0.width > 0 && $0.height > 0 })
            case .failure(let error): XCTFail(error.localizedDescription)
            }
            done.fulfill()
        }
        wait(for: [done], timeout: 10)
    }
    func testNativeProbePreviewAndExport() throws {
        guard let fixtures = ProcessInfo.processInfo.environment["ATIV_TEST_MEDIA"] else {
            throw XCTSkip("Set ATIV_TEST_MEDIA to generated native media fixtures")
        }
        let root = URL(fileURLWithPath: fixtures)
        let image = root.appendingPathComponent("artwork ü.ppm")
        let audio = root.appendingPathComponent("audio ü.wav")
        let output = FileManager.default.temporaryDirectory.appendingPathComponent("ativ-native-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at:output,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:output) }
        let client = EngineClient()
        let probe = expectation(description:"native audio probe")
        client.probe(audio:audio) { result in
            switch result {
            case .success(let duration): XCTAssertEqual(duration ?? 0,1,accuracy:0.05)
            case .failure(let error): XCTFail(error.localizedDescription)
            }
            probe.fulfill()
        }
        wait(for:[probe],timeout:30)
        let preview = expectation(description:"native preview")
        client.preview(image:image,output:output.appendingPathComponent("preview.png"),width:160,height:90,flipHorizontal:true,flipVertical:true) { result in
            switch result {
            case .success(let url): XCTAssertTrue(FileManager.default.fileExists(atPath:url.path))
            case .failure(let error): XCTFail(error.localizedDescription)
            }
            preview.fulfill()
        }
        wait(for:[preview],timeout:30)
        let render = expectation(description:"native export")
        var published = false
        client.render(image:image,audio:audio,output:output.appendingPathComponent("video.mp4"),preset:Preset(platform:"Test",aspect:"16:9",width:160,height:90),bitrate:"128k",fps:30,flipHorizontal:true,flipVertical:false) { event in
            if event.stage == "complete" { published = true }
        } completion: { result in
            if case .failure(let error) = result { XCTFail(error.localizedDescription) }
            XCTAssertTrue(published)
            XCTAssertTrue(FileManager.default.fileExists(atPath:output.appendingPathComponent("video.mp4").path))
            render.fulfill()
        }
        wait(for:[render],timeout:60)
    }

    private func createTestMedia() -> (image: URL, audio: URL, tempDir: URL) {
        let temp = FileManager.default.temporaryDirectory.appendingPathComponent("ativ-test-\(UUID().uuidString)")
        try! FileManager.default.createDirectory(at: temp, withIntermediateDirectories: true)
        let img = temp.appendingPathComponent("artwork.ppm")
        var ppmData = Data("P6\n16 16\n255\n".utf8)
        ppmData.append(Data(repeating: 128, count: 16 * 16 * 3))
        try! ppmData.write(to: img)

        let aud = temp.appendingPathComponent("audio.wav")
        var wavData = Data()
        wavData.append(contentsOf: "RIFF".utf8)
        let totalSize = UInt32(36 + 16000)
        withUnsafeBytes(of: totalSize.littleEndian) { wavData.append(contentsOf: $0) }
        wavData.append(contentsOf: "WAVEfmt ".utf8)
        let fmtChunk: [UInt8] = [16, 0, 0, 0, 1, 0, 1, 0, 0x40, 0x1f, 0, 0, 0x80, 0x3e, 0, 0, 2, 0, 16, 0]
        wavData.append(contentsOf: fmtChunk)
        wavData.append(contentsOf: "data".utf8)
        let dataSize = UInt32(16000)
        withUnsafeBytes(of: dataSize.littleEndian) { wavData.append(contentsOf: $0) }
        wavData.append(Data(repeating: 0, count: 16000))
        try! wavData.write(to: aud)

        return (img, aud, temp)
    }

    func testCancellationBeforeLaunch() throws {
        guard ProcessInfo.processInfo.environment["ATIV_ENGINE_PATH"] != nil else {
            throw XCTSkip("Set ATIV_ENGINE_PATH to test the native process boundary")
        }
        let media = createTestMedia()
        defer { try? FileManager.default.removeItem(at: media.tempDir) }

        let client = EngineClient()
        let output = media.tempDir.appendingPathComponent("cancelled_output.mp4")
        let done = expectation(description: "cancellation before launch")

        client.render(image: media.image, audio: media.audio, output: output, preset: Preset(platform: "Test", aspect: "16:9", width: 160, height: 90), bitrate: "128k", fps: 30, flipHorizontal: false, flipVertical: false) { _ in } completion: { result in
            switch result {
            case .success:
                XCTFail("Should not succeed when cancelled")
            case .failure(let error):
                XCTAssertEqual(error as? EngineClientError, EngineClientError.cancelled)
            }
            XCTAssertFalse(FileManager.default.fileExists(atPath: output.path))
            done.fulfill()
        }
        client.cancelRender()
        wait(for: [done], timeout: 10)
    }

    func testRapidPreviewSuperseding() throws {
        guard ProcessInfo.processInfo.environment["ATIV_ENGINE_PATH"] != nil else {
            throw XCTSkip("Set ATIV_ENGINE_PATH to test the native process boundary")
        }
        let media = createTestMedia()
        defer { try? FileManager.default.removeItem(at: media.tempDir) }

        let client = EngineClient()
        let outA = media.tempDir.appendingPathComponent("prevA.png")
        let outB = media.tempDir.appendingPathComponent("prevB.png")
        let outC = media.tempDir.appendingPathComponent("prevC.png")

        let expA = expectation(description: "preview A")
        let expB = expectation(description: "preview B")
        let expC = expectation(description: "preview C")

        client.preview(image: media.image, output: outA, width: 160, height: 90, flipHorizontal: false, flipVertical: false) { result in
            // A should be cancelled or fail as superseded
            expA.fulfill()
        }
        client.preview(image: media.image, output: outB, width: 160, height: 90, flipHorizontal: false, flipVertical: false) { result in
            // B should be cancelled or fail as superseded
            expB.fulfill()
        }
        client.preview(image: media.image, output: outC, width: 160, height: 90, flipHorizontal: false, flipVertical: false) { result in
            // C should succeed
            if case .failure(let error) = result {
                XCTFail("Latest preview failed: \(error)")
            }
            expC.fulfill()
        }

        wait(for: [expA, expB, expC], timeout: 20)
    }

    @MainActor
    func testRenderStorePreviewStateManagement() async {
        let store = RenderStore()
        XCTAssertFalse(store.isPreviewLoading)
        XCTAssertFalse(store.previewFailed)
        XCTAssertNil(store.previewImage)

        // Clear preview when image is nil
        store.imageURL = nil
        store.refreshPreview()
        XCTAssertFalse(store.isPreviewLoading)
        XCTAssertFalse(store.previewFailed)
        XCTAssertNil(store.previewImage)
    }
}

final class UpdateWorkCoordinationTests: XCTestCase {
    @MainActor
    func testIdleTerminationCanProceed() async {
        let store = RenderStore()
        XCTAssertEqual(store.requestTermination(), .terminateNow)
    }

    @MainActor
    func testTerminationWaitsForActiveExportWithoutCancellingIt() async {
        let store = RenderStore()
        store.isRendering = true
        store.progress = 0.4
        XCTAssertEqual(store.requestTermination(), .terminateLater)
        XCTAssertTrue(store.isRendering)
        XCTAssertEqual(store.progress, 0.4)
        XCTAssertEqual(store.status, "Finishing the current video before quitting…")
        XCTAssertFalse(store.canRender)
        // Reset the bridge's shared work state for subsequent tests.
        store.isRendering = false
    }
}

private final class UpdateControllerDouble: NSObject {
    var manualChecks = 0
    @objc func checkForUpdates(_ sender: Any?) { manualChecks += 1 }
    // Accessing an updater object is deliberately unsupported: the menu action
    // belongs to the controller, as declared in Sparkle's pinned public header.
}

final class ManualUpdateActionTests: XCTestCase {
    func testManualActionReachesController() {
        let controller = UpdateControllerDouble()
        XCTAssertTrue(ATIVCheckForUpdatesWithController(Unmanaged.passUnretained(controller).toOpaque()))
        XCTAssertEqual(controller.manualChecks, 1)
    }
    func testMissingControllerActionFailsGracefully() {
        let unsupported = NSObject()
        XCTAssertFalse(ATIVCheckForUpdatesWithController(Unmanaged.passUnretained(unsupported).toOpaque()))
        XCTAssertFalse(ATIVCheckForUpdatesWithController(nil))
    }
}
