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
}
