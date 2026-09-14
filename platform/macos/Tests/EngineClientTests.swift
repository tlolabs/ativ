import XCTest
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

}
