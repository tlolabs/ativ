import Foundation
import XCTest
@testable import ATIV

private actor StoreRequestLog {
    private(set) var operations: [String] = []
    private(set) var requests: [JSONValue] = []
    func record(_ request: JSONValue) { operations.append(request["operation"]?.stringValue ?? ""); requests.append(request) }
}

private actor StoreResultGate {
    private var continuation: CheckedContinuation<JSONValue, Error>?
    private var earlyResult: JSONValue?
    func wait(started: XCTestExpectation) async throws -> JSONValue {
        started.fulfill()
        if let earlyResult { return earlyResult }
        return try await withCheckedThrowingContinuation { continuation = $0 }
    }
    func finish(_ result: JSONValue) {
        if let continuation { continuation.resume(returning: result); self.continuation = nil }
        else { earlyResult = result }
    }
}

@MainActor
final class TranscriptionStoreTests: XCTestCase {
    private let supported = TranscriptionCapability(isSupported: true, reason: "test helper")
    private var catalog: JSONValue {
        .object(["event": .string("result"), "cachePath": .string("/test/cache"), "models": .array([
            .object(["id": .string("whisper-large-v3"), "displayName": .string("Whisper"), "role": .string("recognizer"), "installed": .bool(true)]),
            .object(["id": .string("qwen3-forced-aligner-0.6b-4bit"), "displayName": .string("Aligner"), "role": .string("aligner"), "installed": .bool(true)])
        ])])
    }
    private var transcript: JSONValue {
        .object(["segments": .array([
            .object(["text": .string("Hello world."), "words": .array([
                .object(["text": .string("Hello"), "startSeconds": .number(1), "endSeconds": .number(1.4)]),
                .object(["text": .string("world."), "startSeconds": .number(1.5), "endSeconds": .number(2)])
            ])])
        ]), "provenance": .object(["engineID": .string("test"), "modelID": .string("whisper-large-v3")]),
           "unknownAdditiveField": .object(["preserve": .bool(true)])])
    }

    private func temporarySources() throws -> (URL, URL, URL) {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("ativ-store-tests-\(UUID())")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let a = root.appendingPathComponent("audio a.wav"), b = root.appendingPathComponent("audio b.wav")
        try Data("audio A".utf8).write(to: a)
        try Data("audio B".utf8).write(to: b)
        return (root, a, b)
    }

    func testUnsupportedPlatformDoesNotLaunchHelper() async {
        let log = StoreRequestLog()
        let store = TranscriptionStore(runner: { request, _ in
            await log.record(request)
            return .object([:])
        }, capability: .init(isSupported: false, reason: "Requires Apple silicon"))
        store.loadCatalog()
        store.modelOperation("install")
        store.transcribe()
        await store.waitForCurrentOperation()
        let operations = await log.operations
        XCTAssertTrue(operations.isEmpty)
        XCTAssertFalse(store.isBusy)
        XCTAssertFalse(store.canTranscribe)
    }

    func testChangedSourceRejectsDelayedTranscriptAndRetainsBusyUntilExit() async throws {
        let (root, a, b) = try temporarySources()
        defer { try? FileManager.default.removeItem(at: root) }
        let catalog = catalog, transcript = transcript
        let gate = StoreResultGate()
        let started = expectation(description: "recognition started")
        let store = TranscriptionStore(runner: { request, progress in
            if request["operation"]?.stringValue == "catalog" { return catalog }
            progress(.object(["message": .string("recognizing")]))
            return try await gate.wait(started: started)
        }, capability: supported)
        var busyTransitions: [Bool] = []
        store.workStateChanged = { busyTransitions.append(store.isBusy) }
        store.loadCatalog()
        await store.waitForCurrentOperation()
        store.setSource(a)
        store.transcribe()
        await fulfillment(of: [started], timeout: 3)
        store.setSource(b)
        XCTAssertTrue(store.isBusy, "Cancellation must await actual helper cleanup")
        await gate.finish(.object(["event": .string("result"), "transcript": transcript]))
        await store.waitForCurrentOperation()
        XCTAssertNil(store.document, "A superseded source cannot receive stale recognition")
        XCTAssertFalse(store.isBusy)
        XCTAssertEqual(store.status, "Audio source changed. Previous operation stopped safely.")
        XCTAssertEqual(busyTransitions, [true, false, true, false])
    }

    func testCatalogCompletesWhenAudioChangesDuringInitialFetch() async throws {
        let (root, a, _) = try temporarySources()
        defer { try? FileManager.default.removeItem(at: root) }
        let gate = StoreResultGate(), catalog = catalog
        let started = expectation(description: "catalog started")
        let store = TranscriptionStore(runner: { _, _ in try await gate.wait(started: started) }, capability: supported)
        store.loadCatalog()
        await fulfillment(of: [started], timeout: 3)
        store.setSource(a)
        XCTAssertTrue(store.isBusy)
        await gate.finish(catalog)
        await store.waitForCurrentOperation()
        XCTAssertEqual(store.models.count, 2)
        XCTAssertTrue(store.canTranscribe)
        XCTAssertEqual(store.status, "Model catalog ready. Install or import a model to begin.")
        XCTAssertNil(store.errorMessage)
    }

    func testModelInstallationCompletesWhenAudioChanges() async throws {
        let (root, a, b) = try temporarySources()
        defer { try? FileManager.default.removeItem(at: root) }
        let gate = StoreResultGate(), catalog = catalog, log = StoreRequestLog()
        let started = expectation(description: "installation started")
        let store = TranscriptionStore(runner: { request, progress in
            await log.record(request)
            if request["operation"]?.stringValue == "catalog" { return catalog }
            let result = try await gate.wait(started: started)
            try Task.checkCancellation()
            progress(.object(["message": .string("Finishing model installation")]))
            return result
        }, capability: supported)
        store.setSource(a)
        store.modelOperation("install")
        await fulfillment(of: [started], timeout: 3)
        store.setSource(b)
        await gate.finish(.object(["event": .string("result")]))
        await store.waitForCurrentOperation()
        let operations = await log.operations
        XCTAssertEqual(operations, ["install", "catalog"])
        XCTAssertEqual(store.models.count, 2)
        XCTAssertEqual(store.status, "Model install complete.")
        XCTAssertNil(store.errorMessage)
        XCTAssertFalse(store.isBusy)
    }

    func testUnchangedEditorBindingPreservesCleanStateAndCaptionPreview() async throws {
        let (root, a, _) = try temporarySources()
        defer { try? FileManager.default.removeItem(at: root) }
        let path = root.appendingPathComponent("saved.json")
        let identity = try await TranscriptionSourceIdentity.fingerprint(of: a)
        try await TranscriptionDocument(source: identity, transcript: transcript).save(to: path, sourceURL: a)
        let cue: JSONValue = .object(["text": .string("Hello world."), "startSeconds": .number(1), "endSeconds": .number(2)])
        let store = TranscriptionStore(runner: { request, _ in
            if request["operation"]?.stringValue == "captions" {
                return .object(["cues": .array([cue]), "srt": .string("SRT"), "webVTT": .string("WEBVTT")])
            }
            return .object(["event": .string("result")])
        }, capability: supported)
        store.setSource(a)
        store.loadDocument(from: path)
        await store.waitForCurrentOperation()
        store.generateCaptions()
        await store.waitForCurrentOperation()
        XCTAssertFalse(store.hasUnsavedChanges)
        XCTAssertEqual(store.cues, [cue])
        store.updateSelectedText("Hello world.")
        XCTAssertFalse(store.hasUnsavedChanges)
        XCTAssertFalse(store.hasPendingTextEdits)
        XCTAssertEqual(store.cues, [cue])
        XCTAssertFalse(store.captionsNeedRefresh)
    }

    func testChangedSettingsRejectDelayedCaptionResult() async throws {
        let (root, a, _) = try temporarySources()
        defer { try? FileManager.default.removeItem(at: root) }
        let path = root.appendingPathComponent("saved.json")
        let identity = try await TranscriptionSourceIdentity.fingerprint(of: a)
        try await TranscriptionDocument(source: identity, transcript: transcript).save(to: path, sourceURL: a)
        let gate = StoreResultGate()
        let started = expectation(description: "caption generation started")
        let store = TranscriptionStore(runner: { request, _ in
            if request["operation"]?.stringValue == "captions" {
                return try await gate.wait(started: started)
            }
            return .object(["event": .string("result")])
        }, capability: supported)
        store.setSource(a)
        store.loadDocument(from: path)
        await store.waitForCurrentOperation()
        store.generateCaptions()
        await fulfillment(of: [started], timeout: 3)
        store.maximumWords = 7
        store.captionSettingsChanged()
        await gate.finish(.object(["cues": .array([.object(["text": .string("stale")])]),
                                   "srt": .string("old SRT"), "webVTT": .string("old VTT")]))
        await store.waitForCurrentOperation()
        XCTAssertTrue(store.cues.isEmpty)
        XCTAssertTrue(store.captionsNeedRefresh)
        XCTAssertTrue(store.hasUnsavedChanges)
        XCTAssertEqual(store.errorMessage, "Caption settings changed. Build the caption preview again.")
    }

    func testDraftRevertRestoresCleanStateWithoutDroppingOtherUnsavedChanges() async throws {
        let (root, a, _) = try temporarySources()
        defer { try? FileManager.default.removeItem(at: root) }
        let path = root.appendingPathComponent("saved.json")
        let identity = try await TranscriptionSourceIdentity.fingerprint(of: a)
        try await TranscriptionDocument(source: identity, transcript: transcript).save(to: path, sourceURL: a)
        let store = TranscriptionStore(runner: { request, _ in
            if request["operation"]?.stringValue == "edit" {
                var transcript = request["transcript"]!.objectValue!
                transcript["segments"] = .array([.object(["text": request["edits"]!.arrayValue!.first!["text"]!, "words": .array([])])])
                return .object(["transcript": .object(transcript)])
            }
            return .object(["event": .string("result")])
        }, capability: supported)
        store.setSource(a)
        store.loadDocument(from: path)
        await store.waitForCurrentOperation()
        store.updateSelectedText("Draft correction.")
        XCTAssertTrue(store.hasUnsavedChanges)
        store.updateSelectedText("Hello world.")
        XCTAssertFalse(store.hasUnsavedChanges)
        store.maximumWords = 7
        store.captionSettingsChanged()
        store.updateSelectedText("Another draft.")
        store.updateSelectedText("Hello world.")
        XCTAssertTrue(store.hasUnsavedChanges, "Reverting text must retain changed caption preferences")
        store.maximumWords = 6
        store.captionSettingsChanged()
        XCTAssertFalse(store.hasUnsavedChanges)
        store.updateSelectedText("Committed correction.")
        store.applyEdits()
        await store.waitForCurrentOperation()
        store.updateSelectedText("Uncommitted revision.")
        store.updateSelectedText("Committed correction.")
        XCTAssertTrue(store.hasUnsavedChanges, "Applied corrections remain unsaved until document publication")
        XCTAssertFalse(store.hasPendingTextEdits)
    }

    func testEditsAreRetainedAcrossSourceChangeAndRealignmentUsesEditedRecord() async throws {
        let (root, a, b) = try temporarySources()
        defer { try? FileManager.default.removeItem(at: root) }
        let catalog = catalog, transcript = transcript
        let log = StoreRequestLog()
        let store = TranscriptionStore(runner: { request, _ in
            await log.record(request)
            switch request["operation"]?.stringValue {
            case "catalog": return catalog
            case "edit":
                var object = request["transcript"]!.objectValue!
                object["segments"] = .array([.object(["text": request["edits"]!.arrayValue!.first!["text"]!, "words": .array([])])])
                object.removeValue(forKey: "alignmentProvenance")
                return .object(["transcript": .object(object)])
            case "align":
                XCTAssertEqual(request["transcript"]?["segments"]?.arrayValue?.first?["text"]?.stringValue, "Corrected text.")
                return .object(["transcript": request["transcript"]!])
            default: return .object(["transcript": transcript])
            }
        }, capability: supported)
        store.loadCatalog()
        await store.waitForCurrentOperation()
        store.setSource(a)
        store.transcribe()
        await store.waitForCurrentOperation()
        XCTAssertTrue(store.hasWordTiming)
        store.updateSelectedText("Corrected text.")
        XCTAssertFalse(store.hasWordTiming, "Draft corrections must disable timed output immediately")
        store.setSource(b)
        XCTAssertEqual(store.selectedSegmentText, "Corrected text.")
        XCTAssertFalse(store.sourceMatchesDocument)
        XCTAssertFalse(store.canAlign)
        store.setSource(a)
        await store.waitForSourceIdentity()
        XCTAssertTrue(store.canAlign)
        store.align()
        await store.waitForCurrentOperation()
        let operations = await log.operations
        XCTAssertEqual(operations.filter { $0 == "transcribe" }.count, 1)
        XCTAssertEqual(Array(operations.suffix(2)), ["edit", "align"])
        XCTAssertFalse(store.hasPendingTextEdits)
        XCTAssertNotNil(store.document?.transcript["unknownAdditiveField"])
    }

    func testMultipleDraftsUseOneAtomicHelperRequest() async throws {
        let (root, a, _) = try temporarySources()
        defer { try? FileManager.default.removeItem(at: root) }
        var payload = transcript.objectValue!
        payload["segments"] = .array(Array(repeating: transcript["segments"]!.arrayValue![0], count: 3))
        let original = JSONValue.object(payload), log = StoreRequestLog()
        let identity = try await TranscriptionSourceIdentity.fingerprint(of: a)
        let path = root.appendingPathComponent("batch.json")
        try await TranscriptionDocument(source: identity, transcript: original).save(to: path, sourceURL: a)
        let store = TranscriptionStore(runner: { request, _ in
            await log.record(request)
            if request["operation"]?.stringValue != "edit" { return .object(["event": .string("result")]) }
            XCTAssertNil(request["segmentIndex"])
            let edits = request["edits"]!.arrayValue!
            XCTAssertEqual(edits.compactMap { $0["segmentIndex"]?.doubleValue }, [0, 2])
            var object = request["transcript"]!.objectValue!
            var segments = object["segments"]!.arrayValue!
            for edit in edits {
                let index = Int(edit["segmentIndex"]!.doubleValue!)
                var segment = segments[index].objectValue!
                segment["text"] = edit["text"]
                segment["words"] = .array([])
                segments[index] = .object(segment)
            }
            object["segments"] = .array(segments)
            return .object(["transcript": .object(object)])
        }, capability: supported)
        store.setSource(a)
        store.loadDocument(from: path)
        await store.waitForCurrentOperation()
        store.selectedSegment = 2
        store.updateSelectedText("Last corrected.")
        store.selectedSegment = 0
        store.updateSelectedText("First corrected.")
        store.applyEdits()
        await store.waitForCurrentOperation()
        let operations = await log.operations
        XCTAssertEqual(operations.filter { $0 == "edit" }.count, 1)
        XCTAssertEqual(store.segments[0]["text"], .string("First corrected."))
        XCTAssertEqual(store.segments[2]["text"], .string("Last corrected."))
        XCTAssertEqual(store.segments[1], original["segments"]!.arrayValue![1])
        XCTAssertNotNil(store.document?.transcript["unknownAdditiveField"])
        XCTAssertFalse(store.hasPendingTextEdits)
        XCTAssertTrue(store.hasUnsavedChanges)
        XCTAssertFalse(store.hasWordTiming)
    }

    func testFailedBatchRetainsCanonicalTranscriptAndEveryDraft() async throws {
        let (root, a, _) = try temporarySources()
        defer { try? FileManager.default.removeItem(at: root) }
        let original = transcript
        let identity = try await TranscriptionSourceIdentity.fingerprint(of: a)
        let path = root.appendingPathComponent("batch-failure.json")
        try await TranscriptionDocument(source: identity, transcript: original).save(to: path, sourceURL: a)
        let store = TranscriptionStore(runner: { request, _ in
            if request["operation"]?.stringValue == "edit" { throw NSError(domain: "TestBatch", code: 1) }
            return .object(["event": .string("result")])
        }, capability: supported)
        store.setSource(a)
        store.loadDocument(from: path)
        await store.waitForCurrentOperation()
        store.updateSelectedText("Retained draft.")
        store.applyEdits()
        await store.waitForCurrentOperation()
        XCTAssertEqual(store.document?.transcript, original)
        XCTAssertEqual(store.selectedSegmentText, "Retained draft.")
        XCTAssertTrue(store.hasPendingTextEdits)
        XCTAssertTrue(store.hasUnsavedChanges)
        XCTAssertNotNil(store.errorMessage)
    }

    func testSourceChangedDuringBatchRetainsDraftsAndRejectsReturnedTranscript() async throws {
        let (root, a, b) = try temporarySources()
        defer { try? FileManager.default.removeItem(at: root) }
        let original = transcript
        let identity = try await TranscriptionSourceIdentity.fingerprint(of: a)
        let path = root.appendingPathComponent("batch-cancel.json")
        try await TranscriptionDocument(source: identity, transcript: original).save(to: path, sourceURL: a)
        let gate = StoreResultGate(), started = expectation(description: "batch started")
        let store = TranscriptionStore(runner: { request, _ in
            if request["operation"]?.stringValue == "edit" { return try await gate.wait(started: started) }
            return .object(["event": .string("result")])
        }, capability: supported)
        store.setSource(a)
        store.loadDocument(from: path)
        await store.waitForCurrentOperation()
        store.updateSelectedText("Retained draft.")
        store.applyEdits()
        await fulfillment(of: [started], timeout: 3)
        store.setSource(b)
        await gate.finish(.object(["transcript": .object(["segments": .array([])])]))
        await store.waitForCurrentOperation()
        XCTAssertEqual(store.document?.transcript, original)
        XCTAssertEqual(store.selectedSegmentText, "Retained draft.")
        XCTAssertTrue(store.hasPendingTextEdits)
        XCTAssertTrue(store.hasUnsavedChanges)
        XCTAssertFalse(store.isBusy)
        XCTAssertEqual(store.status, "Audio source changed. Previous operation stopped safely.")
    }

    func testImportedHugeCaptionPreferencesAreClampedWithoutIntegerTrap() async throws {
        let (root, a, _) = try temporarySources()
        defer { try? FileManager.default.removeItem(at: root) }
        let identity = try await TranscriptionSourceIdentity.fingerprint(of: a)
        let document = TranscriptionDocument(source: identity, transcript: transcript, captionPreferences: .object([
            "maximumWords": .number(1e300), "maximumCharacters": .number(1e300), "sourceEndSeconds": .null
        ]))
        let path = root.appendingPathComponent("huge-preferences.json")
        try await document.save(to: path, sourceURL: a)
        let store = TranscriptionStore(runner: { _, _ in .object(["event": .string("result")]) }, capability: supported)
        store.setSource(a)
        store.loadDocument(from: path)
        await store.waitForCurrentOperation()
        XCTAssertEqual(store.maximumWords, 30)
        XCTAssertEqual(store.maximumCharacters, 200)
        XCTAssertEqual(store.trimEnd, "")
        XCTAssertFalse(store.hasUnsavedChanges)
        XCTAssertNotNil(store.document?.transcript["unknownAdditiveField"])
    }

    func testMalformedManualTrimDoesNotStartCaptionExport() async throws {
        let (root, a, _) = try temporarySources()
        defer { try? FileManager.default.removeItem(at: root) }
        let catalog = catalog, transcript = transcript
        let log = StoreRequestLog()
        let store = TranscriptionStore(runner: { request, _ in
            await log.record(request)
            return request["operation"]?.stringValue == "catalog" ? catalog : .object(["transcript": transcript])
        }, capability: supported)
        store.loadCatalog()
        await store.waitForCurrentOperation()
        store.setSource(a)
        store.transcribe()
        await store.waitForCurrentOperation()
        store.trimEnd = "invalid trim"
        store.generateCaptions()
        await store.waitForCurrentOperation()
        let operations = await log.operations
        XCTAssertFalse(operations.contains("captions"))
        XCTAssertNotNil(store.errorMessage)
        XCTAssertTrue(store.cues.isEmpty)
        XCTAssertNotNil(store.document)
    }
}
