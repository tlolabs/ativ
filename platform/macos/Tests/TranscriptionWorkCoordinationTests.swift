import AppKit
import XCTest
@testable import ATIV

@MainActor
final class TranscriptionWorkCoordinationTests: XCTestCase {
    func testTerminationJoinsOptionalWorkAfterMediaWorkersBecomeIdle() async {
        let store = RenderStore()
        let drain = expectation(description: "Optional work is asked to drain")
        store.additionalWorkInProgress = { true }
        store.drainAdditionalWork = { _ in
            // Retain the completion: a model kernel has not exited yet, so the
            // application must not receive permission to terminate here.
            drain.fulfill()
        }
        XCTAssertEqual(store.requestTermination(), .terminateLater)
        await fulfillment(of: [drain], timeout: 2)
        XCTAssertFalse(store.canRender)
    }
}
