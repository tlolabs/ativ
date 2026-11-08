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
        let previous = Data("previous completed export".utf8)
        try previous.write(to: output)
        let done = expectation(description: "cancellation before launch")

        client.render(image: media.image, audio: media.audio, output: output, preset: Preset(platform: "Test", aspect: "16:9", width: 160, height: 90), bitrate: "128k", fps: 30, flipHorizontal: false, flipVertical: false) { _ in } completion: { result in
            switch result {
            case .success:
                XCTFail("Should not succeed when cancelled")
            case .failure(let error):
                XCTAssertEqual(error as? EngineClientError, EngineClientError.cancelled)
            }
            XCTAssertEqual(try? Data(contentsOf: output), previous)
            done.fulfill()
        }
        client.cancelRender()
        wait(for: [done], timeout: 10)
    }

    func testCancellationAfterLaunchPreservesExistingDestination() throws {
        guard ProcessInfo.processInfo.environment["ATIV_ENGINE_PATH"] != nil else {
            throw XCTSkip("Set ATIV_ENGINE_PATH")
        }
        let media = createTestMedia()
        defer { try? FileManager.default.removeItem(at: media.tempDir) }
        let output = media.tempDir.appendingPathComponent("existing.mp4")
        let previous = Data("previous completed export".utf8)
        try previous.write(to: output)
        let client = EngineClient()
        let done = expectation(description: "cancel running export")
        var requested = false
        client.render(image: media.image, audio: media.audio, output: output,
                      preset: Preset(platform: "Test", aspect: "16:9", width: 1920, height: 1080),
                      bitrate: "128k", fps: 30, flipHorizontal: false, flipVertical: false) { event in
            if event.stage == "validating" {
                requested = true
                client.cancelRender()
            }
        } completion: { result in
            XCTAssertTrue(requested)
            switch result {
            case .success: XCTFail("Expected cancellation")
            case .failure(let error): XCTAssertEqual(error as? EngineClientError, .cancelled)
            }
            XCTAssertEqual(try? Data(contentsOf: output), previous)
            done.fulfill()
        }
        wait(for: [done], timeout: 15)
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

    // These process doubles isolate host lifecycle behavior; they do not claim
    // coverage of Core, FFmpeg, or authenticated runtime acquisition.
    private func withEngineDouble(_ script: String, perform: (URL) throws -> Void) throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("ativ-engine-double-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let executable = root.appendingPathComponent("engine")
        try Data(("#!/bin/sh\n" + script).utf8).write(to: executable)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executable.path)
        let previous = ProcessInfo.processInfo.environment["ATIV_ENGINE_PATH"]
        setenv("ATIV_ENGINE_PATH", executable.path, 1)
        defer {
            if let previous { setenv("ATIV_ENGINE_PATH", previous, 1) }
            else { unsetenv("ATIV_ENGINE_PATH") }
        }
        try perform(root)
    }

    func testFailedPreviewPreservesExistingDestination() throws {
        try withEngineDouble("echo '{\"event\":\"error\",\"message\":\"invalid artwork\"}'\nexit 1\n") { root in
            let output = root.appendingPathComponent("existing.png")
            let previous = Data("previous completed preview".utf8)
            try previous.write(to: output)
            let done = expectation(description: "failed preview preserves destination")
            let client = EngineClient()
            client.preview(image: root.appendingPathComponent("broken.png"), output: output, width: 160, height: 90,
                           flipHorizontal: false, flipVertical: false) { result in
                if case .success = result { XCTFail("Expected invalid artwork failure") }
                XCTAssertEqual(try? Data(contentsOf: output), previous)
                done.fulfill()
            }
            wait(for: [done], timeout: 5)
        }
    }

    func testPublishedExportWinsOverLateCancellation() throws {
        try withEngineDouble("echo '{\"event\":\"stage\",\"stage\":\"complete\"}'\nread cancellation\nexit 130\n") { root in
            let client = EngineClient()
            let done = expectation(description: "published export")
            client.render(image: root.appendingPathComponent("image.png"), audio: root.appendingPathComponent("audio.wav"),
                          output: root.appendingPathComponent("output.mp4"),
                          preset: Preset(platform: "Test", aspect: "16:9", width: 160, height: 90),
                          bitrate: "128k", fps: 30, flipHorizontal: false, flipVertical: false) { item in
                if item.stage == "complete" { client.cancelRender() }
            } completion: { result in
                if case .failure(let error) = result { XCTFail("Publication must remain successful: \(error)") }
                done.fulfill()
            }
            wait(for: [done], timeout: 5)
        }
    }

    func testWorkersSerializeAcrossClientsAndDrainBeforeIdle() throws {
        try withEngineDouble("echo start >> \"$0.log\"\nsleep 0.1\necho end >> \"$0.log\"\necho '{\"event\":\"probe\",\"duration_seconds\":1}'\n") { root in
            let clients = [EngineClient(), EngineClient()]
            let done = expectation(description: "both operations finish")
            done.expectedFulfillmentCount = 2
            for client in clients {
                client.probe(audio: root.appendingPathComponent("audio.wav")) { result in
                    if case .failure(let error) = result { XCTFail(error.localizedDescription) }
                    done.fulfill()
                }
                XCTAssertTrue(client.hasPendingWork)
            }
            let idle = expectation(description: "worker queue drained")
            clients[0].whenIdle {
                XCTAssertFalse(clients.contains { $0.hasPendingWork })
                let log = try? String(contentsOf: root.appendingPathComponent("engine.log"), encoding: .utf8)
                XCTAssertEqual(log, "start\nend\nstart\nend\n")
                idle.fulfill()
            }
            wait(for: [done, idle], timeout: 5)
        }
    }

    @MainActor
    func testStaleAudioProbeCannotReplaceActiveExportStatus() throws {
        try withEngineDouble("exit 130\n") { root in
            let store = RenderStore()
            store.setAudio(root.appendingPathComponent("audio.wav"))
            store.isRendering = true
            defer { store.isRendering = false }
            store.status = "Creating video…"
            let done = expectation(description: "stale probe callback ignored")
            // A queue barrier waits for the process-double probe and its main
            // queue callback before checking the active export's UI state.
            EngineClient().whenIdle {
                DispatchQueue.main.async {
                    XCTAssertNil(store.errorMessage)
                    XCTAssertEqual(store.status, "Creating video…")
                    done.fulfill()
                }
            }
            wait(for: [done], timeout: 5)
        }
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

final class PerformanceRegressionTests: XCTestCase {
    func testStreamEveryBoundaryAndEOF() {
        let wire = Data("{\"event\":\"stage\",\"stage\":\"café 🎬\"}\n\ninvalid\n{\"event\":\"progress\",\"fraction\":0.5}\n{\"event\":\"complete\"}".utf8)
        for cut in 0...wire.count {
            var parser = EngineEventStream()
            var events: [String] = []
            parser.consume(Data(wire.prefix(cut))) { events.append($0.event) }
            parser.consume(Data()) { events.append($0.event) }
            parser.consume(Data(wire.dropFirst(cut))) { events.append($0.event) }
            parser.consume(Data(), endOfFile: true) { events.append($0.event) }
            XCTAssertEqual(events, ["stage", "progress", "complete"], "cut \(cut)")
        }
    }

    func testStreamLargeMalformedAndOversizedLinesRecover() {
        var parser = EngineEventStream()
        var events: [EngineEvent] = []
        let large = Data(("{\"event\":\"stage\",\"stage\":\"" + String(repeating: "é", count: 100_000) + "\"}\n").utf8)
        for byte in large { parser.consume(Data([byte])) { events.append($0) } }
        XCTAssertEqual(events.count, 1)
        for _ in 0...EngineEventStream.maximumLineBytes / 65536 {
            parser.consume(Data(repeating: 120, count: 65536)) { events.append($0) }
            XCTAssertLessThanOrEqual(parser.pending.count, EngineEventStream.maximumLineBytes)
        }
        parser.consume(Data("\n{\"event\":\"complete\"}\n{".utf8)) { events.append($0) }
        parser.consume(Data(), endOfFile: true) { events.append($0) }
        XCTAssertEqual(events.map(\.event), ["stage", "complete"])
        XCTAssertTrue(parser.pending.isEmpty)
    }

    @MainActor
    func testPresetReplacementAndRestoredInvalidSelections() async {
        let store = RenderStore()
        let a = Preset(platform: "A", aspect: "wide", width: 160, height: 90)
        let b = Preset(platform: "B", aspect: "square", width: 90, height: 90)
        store.presets = [a, a, b]
        XCTAssertEqual(store.platforms, ["A", "B"])
        XCTAssertEqual(store.selectedPreset, a)
        store.selectedPlatform = "B"
        XCTAssertEqual(store.aspects, ["square"])
        XCTAssertEqual(store.resolutions, [b])
        XCTAssertEqual(store.selectedPreset, b)
        store.selectedAspect = "invalid"
        store.selectedPreset = a
        XCTAssertEqual(store.selectedAspect, "square")
        XCTAssertEqual(store.selectedPreset, b)
        store.presets = [a]
        XCTAssertEqual(store.selectedPlatform, "A")
        XCTAssertEqual(store.selectedPreset, a)
        store.presets = []
        XCTAssertTrue(store.platforms.isEmpty)
        XCTAssertTrue(store.aspects.isEmpty)
        XCTAssertTrue(store.resolutions.isEmpty)
        XCTAssertNil(store.selectedPreset)
        store.presets = [b]
        XCTAssertEqual(store.selectedPreset, b)
    }

    func testFileSelectionRowExtractsURLFromVariousTypes() {
        let expectedURL = URL(fileURLWithPath: "/tmp/sample.mp3")
        XCTAssertEqual(FileSelectionRow.url(from: expectedURL), expectedURL)
        let nsURL = NSURL(fileURLWithPath: "/tmp/sample.mp3")
        XCTAssertEqual(FileSelectionRow.url(from: nsURL), expectedURL)
        let data = expectedURL.dataRepresentation
        XCTAssertEqual(FileSelectionRow.url(from: data), expectedURL)
        let stringData = Data("/tmp/sample.mp3".utf8)
        XCTAssertEqual(FileSelectionRow.url(from: stringData), expectedURL)
        XCTAssertEqual(FileSelectionRow.url(from: "/tmp/sample.mp3"), expectedURL)
        XCTAssertEqual(FileSelectionRow.url(from: NSString(string: "/tmp/sample.mp3")), expectedURL)
        XCTAssertEqual(FileSelectionRow.url(from: "file:///tmp/sample.mp3"), expectedURL)
        XCTAssertNil(FileSelectionRow.url(from: "not-a-url"))
        XCTAssertNil(FileSelectionRow.url(from: nil))
    }

    func testFileSelectionRowPreservesRawPathsAndRejectsRemoteURLs() {
        let path = "/tmp/100%25#mix?.mp3 "
        let expected = URL(fileURLWithPath: path)
        for item: Any in [path, NSString(string: path), Data(path.utf8), expected, expected as NSURL, expected.absoluteString, Data(expected.absoluteString.utf8)] {
            XCTAssertEqual(FileSelectionRow.url(from: item), expected)
        }
        for text in ["https://example.com/tmp/sample.mp3", "ftp://example.com/tmp/sample.mp3", "relative.mp3", "file:relative.mp3"] {
            XCTAssertNil(FileSelectionRow.url(from: text))
            XCTAssertNil(FileSelectionRow.url(from: Data(text.utf8)))
            XCTAssertNil(FileSelectionRow.url(from: URL(string: text)!))
            XCTAssertNil(FileSelectionRow.url(from: URL(string: text)! as NSURL))
        }
        XCTAssertNil(FileSelectionRow.url(from: Data([0xff, 0xfe])))
        XCTAssertNil(FileSelectionRow.url(from: "/tmp/invalid\0.mp3"))
    }

    @MainActor
    func testRenderStoreRecognizesSourceAliasesAndPreservesCustomOutput() throws {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("ativ-collisions-\(UUID().uuidString)")
        let media = root.appendingPathComponent("media")
        let alias = root.appendingPathComponent("alias")
        try FileManager.default.createDirectory(at: media, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        try FileManager.default.createSymbolicLink(at: alias, withDestinationURL: media)
        let image = media.appendingPathComponent("sample.mp4")
        try Data("artwork".utf8).write(to: image)
        let store = RenderStore()
        store.audioURL = alias.appendingPathComponent("sample.wav")
        store.outputURL = alias.appendingPathComponent("sample.mp4")
        store.setImage(image)
        XCTAssertEqual(store.outputURL, alias.appendingPathComponent("sample-video.mp4"))
        store.presets = [Preset(platform: "Test", aspect: "16:9", width: 160, height: 90)]
        XCTAssertTrue(store.canRender)

        let hardLink = media.appendingPathComponent("hard-link.mp4")
        try FileManager.default.linkItem(at: image, to: hardLink)
        store.setOutput(hardLink)
        XCTAssertFalse(store.canRender)
        store.render(replacingExisting: true)
        XCTAssertEqual(store.errorMessage, "The output destination must be separate from the image and audio source files.")
        XCTAssertEqual(try Data(contentsOf: image), Data("artwork".utf8))

        let custom = media.appendingPathComponent("custom.mp4")
        store.setOutput(custom)
        store.setImage(alias.appendingPathComponent("sample.mp4"))
        XCTAssertEqual(store.outputURL, custom)
        XCTAssertTrue(store.canRender)
    }

    @MainActor
    func testRenderStoreOutputCollisionResolution() {
        let store = RenderStore()
        let audioURL = URL(fileURLWithPath: "/tmp/sample.wav")
        let imageURL = URL(fileURLWithPath: "/tmp/sample.mp4")
        store.setAudio(audioURL)
        XCTAssertEqual(store.outputURL, URL(fileURLWithPath: "/tmp/sample.mp4"))
        store.setImage(imageURL)
        XCTAssertNotEqual(store.outputURL, imageURL)
        XCTAssertEqual(store.outputURL, URL(fileURLWithPath: "/tmp/sample-video.mp4"))

        // Test multi-step collision resolution when audio is sample.mp4 and image is sample-video.mp4
        let mp4Audio = URL(fileURLWithPath: "/tmp/sample.mp4")
        let videoCollisionImage = URL(fileURLWithPath: "/tmp/sample-video.mp4")
        store.setAudio(mp4Audio)
        store.setImage(videoCollisionImage)
        XCTAssertNotEqual(store.outputURL, videoCollisionImage)
        XCTAssertNotEqual(store.outputURL, mp4Audio)
        XCTAssertEqual(store.outputURL, URL(fileURLWithPath: "/tmp/sample-video-video.mp4"))
    }
}
