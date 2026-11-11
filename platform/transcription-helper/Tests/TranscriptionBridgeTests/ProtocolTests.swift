import AVIDTranscription
import Foundation
import XCTest
@testable import TranscriptionBridge

final class ProtocolTests: XCTestCase {
    private func request(_ value: [String: Any]) throws -> HelperRequest {
        try JSONDecoder().decode(HelperRequest.self, from: JSONSerialization.data(withJSONObject: value))
    }

    private func transcriptObject() throws -> [String: Any] {
        let word = try TranscriptWord(text: "Hello", startSeconds: 12.5, endSeconds: 13.5)
        let transcript = try Transcript(segments: [TranscriptSegment(text: "Hello", words: [word], startSeconds: 12.5, endSeconds: 13.5)],
            language: "en", provenance: TranscriptProvenance(engineID: "recognizer", modelID: "original"),
            alignmentProvenance: TranscriptProvenance(engineID: "aligner", modelID: "alignment"))
        return try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(transcript)) as? [String: Any])
    }

    func testEditInvalidatesOnlySharedContractTimingAndKeepsRecognitionProvenance() throws {
        let input = try request(["operation": "edit", "transcript": transcriptObject(), "segmentIndex": 0, "text": "Hello, corrected."])
        let edited = try input.editingTranscript()
        XCTAssertEqual(edited.text, "Hello, corrected.")
        XCTAssertEqual(edited.provenance.modelID, "original")
        XCTAssertNil(edited.alignmentProvenance)
        XCTAssertFalse(edited.hasCompleteWordTiming)
        XCTAssertThrowsError(try CaptionBuilder.cues(from: edited))
    }

    func testBatchEditsMatchSequentialCanonicalCorrectionsWithOneArrayUpdate() throws {
        var raw = try transcriptObject()
        let one = (raw["segments"] as! [[String: Any]])[0]
        raw["segments"] = [one, one, one]
        let input = try request(["operation": "edit", "transcript": raw,
            "edits": [["segmentIndex": 2, "text": "Last corrected."], ["segmentIndex": 0, "text": "First corrected."]]])
        let original = try input.requiredTranscript()
        let edited = try input.editingTranscript()
        XCTAssertEqual(edited, try original.correctingSegment(at: 2, text: "Last corrected.").correctingSegment(at: 0, text: "First corrected."))
        XCTAssertEqual(edited.segments[1], original.segments[1])
        XCTAssertTrue(edited.segments[0].words.isEmpty)
        XCTAssertTrue(edited.segments[2].words.isEmpty)
        XCTAssertEqual(edited.language, original.language)
        XCTAssertEqual(edited.provenance, original.provenance)
        XCTAssertNil(edited.alignmentProvenance)
        XCTAssertEqual(try input.requiredTranscript(), original)
    }

    func testBatchRejectsInvalidDuplicateAndAmbiguousEditsWithoutChangingOriginal() throws {
        let raw = try transcriptObject()
        let cases: [[String: Any]] = [
            ["edits": [["segmentIndex": 0, "text": "Valid"], ["segmentIndex": 1, "text": "Invalid"]]],
            ["edits": [["segmentIndex": 0, "text": "One"], ["segmentIndex": 0, "text": "Two"]]],
            ["edits": [["segmentIndex": 0, "text": "Batch"]], "segmentIndex": 0, "text": "Single"]
        ]
        for fields in cases {
            let input = try request(fields.merging(["operation": "edit", "transcript": raw]) { _, value in value })
            let original = try input.requiredTranscript()
            XCTAssertThrowsError(try input.editingTranscript())
            XCTAssertEqual(try input.requiredTranscript(), original)
            XCTAssertNotNil(original.alignmentProvenance)
        }
        let empty = try request(["operation": "edit", "transcript": raw, "edits": []])
        XCTAssertEqual(try empty.editingTranscript(), empty.transcript)
    }

    func testCancelledBatchDoesNotReturnPartialTranscript() async throws {
        let input = try request(["operation": "edit", "transcript": transcriptObject(), "edits": [["segmentIndex": 0, "text": "Cancelled"]]])
        let work = Task.detached {
            while !Task.isCancelled { await Task.yield() }
            return try input.editingTranscript()
        }
        work.cancel()
        do { _ = try await work.value; XCTFail("Expected cancellation") }
        catch { XCTAssertTrue(error is CancellationError) }
        XCTAssertEqual(try input.requiredTranscript().text, "Hello")
    }

    func testCaptionWindowUsesOriginalSourceClockOnce() throws {
        let input = try request(["operation": "captions", "transcript": transcriptObject(),
            "captionWindow": ["sourceStartSeconds": 13, "sourceEndSeconds": 14, "timelineStartSeconds": 2],
            "captionOptions": ["maximumWords": 1]])
        let result = try input.captionResult()
        XCTAssertEqual(result.cues?.first?.startSeconds, 2)
        XCTAssertEqual(result.cues?.first?.endSeconds, 2.5)
        XCTAssertTrue(result.srt?.contains("00:00:02,000 --> 00:00:02,500") == true)
        XCTAssertTrue(result.webVTT?.hasPrefix("WEBVTT\n") == true)
        XCTAssertEqual(try input.requiredTranscript().segments[0].words[0].startSeconds, 12.5)
    }

    func testPartialCaptionSettingsInheritCoreDefaultsAndPreserveExplicitValues() throws {
        let defaults = CaptionOptions()
        let window = CaptionWindow()
        let input = try request(["operation": "captions", "transcript": transcriptObject(),
            "captionOptions": ["maximumWords": 1, "maximumPauseSeconds": 0],
            "captionWindow": ["timelineStartSeconds": 2]])
        XCTAssertEqual(input.captionOptions?.value, CaptionOptions(
            maximumCharacters: defaults.maximumCharacters, maximumWords: 1,
            maximumDurationSeconds: defaults.maximumDurationSeconds, maximumPauseSeconds: 0))
        XCTAssertEqual(input.captionWindow?.value, CaptionWindow(
            sourceStartSeconds: window.sourceStartSeconds, sourceEndSeconds: window.sourceEndSeconds,
            timelineStartSeconds: 2))
        let empty = try request(["operation": "captions", "transcript": transcriptObject(),
            "captionOptions": [:], "captionWindow": [:]])
        XCTAssertEqual(empty.captionOptions?.value, defaults)
        XCTAssertEqual(empty.captionWindow?.value, window)
        XCTAssertEqual(try empty.captionResult().cues, try CaptionBuilder.cues(from: empty.requiredTranscript()))
    }

    func testCanonicalDecoderRejectsMalformedTimestampsAndUnknownTiming() throws {
        var transcript = try transcriptObject()
        transcript["segments"] = [["text": "bad", "words": [["text": "bad", "startSeconds": 4, "endSeconds": 2]]]]
        XCTAssertThrowsError(try request(["operation": "validate", "transcript": transcript]))
        transcript["segments"] = [["text": "bad", "words": [["text": "bad", "startSeconds": 1, "endSeconds": 2, "timingMethod": "madeUp"]]]]
        XCTAssertThrowsError(try request(["operation": "validate", "transcript": transcript]))
    }

    func testEditRejectsInvalidIndexAndCaptionsRejectInvalidOptions() throws {
        let edit = try request(["operation": "edit", "transcript": transcriptObject(), "segmentIndex": 1, "text": "Oops"])
        XCTAssertThrowsError(try edit.editingTranscript())
        let captions = try request(["operation": "captions", "transcript": transcriptObject(), "captionOptions": ["maximumWords": 0]])
        XCTAssertThrowsError(try captions.captionResult())
    }

    func testLocalPathsAndOffsetsMustRemainExplicit() throws {
        let input = try request(["operation": "transcribe", "sourceOffset": -1])
        XCTAssertThrowsError(try input.validatedSourceOffset())
        XCTAssertThrowsError(try input.requiredLocalURL("https://example.com/audio.wav", label: "Audio"))
        XCTAssertThrowsError(try input.requiredLocalURL("relative.wav", label: "Audio"))
        XCTAssertEqual(try input.requiredLocalURL("/tmp/$(literal)#a.wav", label: "Audio").path, "/tmp/$(literal)#a.wav")
    }

    func testCanonicalTranscriptRoundTripsWithoutDroppingProvenance() throws {
        let input = try request(["operation": "validate", "transcript": transcriptObject()])
        let result = HelperEvent(transcript: try input.requiredTranscript())
        let decoded = try JSONDecoder().decode(HelperEvent.self, from: JSONEncoder().encode(result))
        XCTAssertEqual(decoded.transcript, input.transcript)
        XCTAssertEqual(decoded.protocolVersion, 1)
    }
}
