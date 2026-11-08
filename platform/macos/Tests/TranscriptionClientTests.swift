// SPDX-License-Identifier: GPL-3.0-or-later
import Foundation
import XCTest
@testable import ATIV

final class TranscriptionClientTests: XCTestCase {
    private func temporaryDirectory() throws -> URL {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("ativ-transcription-test-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        return root
    }
    private func executable(_ contents: String, in root: URL) throws -> URL {
        let url = root.appendingPathComponent("helper with spaces $literal")
        try Data(("#!/bin/sh\n" + contents).utf8).write(to: url)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: url.path)
        return url
    }
    func testCapabilitiesDoNotRaiseExistingPlatformFloor() {
        XCTAssertFalse(TranscriptionClient.capability(osMajorVersion: 14, isAppleSilicon: false, helperExists: true).isSupported)
        XCTAssertFalse(TranscriptionClient.capability(osMajorVersion: 13, isAppleSilicon: true, helperExists: true).isSupported)
        XCTAssertFalse(TranscriptionClient.capability(osMajorVersion: 14, isAppleSilicon: true, helperExists: false).isSupported)
        XCTAssertTrue(TranscriptionClient.capability(osMajorVersion: 14, isAppleSilicon: true, helperExists: true).isSupported)
    }
    func testCapabilityRequiresNestedAppAndItsPackagedResources() throws {
        let root = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: root) }
        let application = root.appendingPathComponent("ATIV.app")
        let helper = TranscriptionClient.packagedHelperURL(in: application)
        XCTAssertEqual(helper.path, application.path + "/Contents/Helpers/ATIVTranscriptionHelper.app/Contents/MacOS/ATIVTranscriptionHelper")
        try FileManager.default.createDirectory(at: helper.deletingLastPathComponent(), withIntermediateDirectories: true)
        try Data("#!/bin/sh\nexit 0\n".utf8).write(to: helper)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: helper.path)
        XCTAssertFalse(TranscriptionClient.packagedHelperExists(at: helper))
        let contents = helper.deletingLastPathComponent().deletingLastPathComponent()
        let resources = [application.appendingPathComponent("Contents/Resources/transcription-package.json"),
                         contents.appendingPathComponent("Resources/AVIDTranscription_AVIDTranscription.bundle/Contents/Resources/models.json"),
                         contents.appendingPathComponent("Resources/mlx-swift_Cmlx.bundle/Contents/Resources/default.metallib")]
        for url in resources {
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try Data("fixture".utf8).write(to: url)
        }
        // Different supported Swift toolchains emit different compatibility dylibs;
        // the UI must accept a verified package that does not import Span.
        XCTAssertFalse(FileManager.default.fileExists(atPath: contents.appendingPathComponent("Frameworks/libswiftCompatibilitySpan.dylib").path))
        XCTAssertTrue(TranscriptionClient.packagedHelperExists(at: helper))
        for resource in resources {
            try FileManager.default.removeItem(at: resource)
            XCTAssertFalse(TranscriptionClient.packagedHelperExists(at: helper), resource.path)
            try Data("fixture".utf8).write(to: resource)
        }
    }
    func testResultWaitsForProcessExitAndArgumentsAreSeparate() async throws {
        let root = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: root) }
        let helper = try executable("""
        [ "$#" = 2 ] && [ "$1" = '--request' ] && [ -f "$2" ] || exit 5
        echo '{"event":"progress","message":"local"}'
        echo '{"event":"result","value":"café 🎬"}'
        /bin/sleep 0.1
        echo drained > "$0.done"
        """, in: root)
        let client = TranscriptionClient(testExecutable: helper)
        let result = try await client.run(request: .object(["operation": .string("catalog")]))
        XCTAssertEqual(result["value"], .string("café 🎬"))
        XCTAssertTrue(FileManager.default.fileExists(atPath: helper.path + ".done"))
        XCTAssertFalse(client.hasPendingWork)
    }
    func testChunkedResponseAndUnterminatedFinalLinePreserveUnicode() async throws {
        let root = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: root) }
        let text = String(repeating: "café 🎬 ", count: 4096)
        let result = JSONValue.object(["event": .string("result"), "value": .string(text)])
        var response = Data("{\"event\":\"progress\",\"message\":\"reading\"}\n".utf8)
        response.append(try JSONEncoder().encode(result))
        let helper = try executable("/bin/cat \"$0.response\"\n", in: root)
        try response.write(to: URL(fileURLWithPath: helper.path + ".response"))
        let value = try await TranscriptionClient(testExecutable: helper).run(request: .object([:]))
        XCTAssertEqual(value["value"], .string(text))
    }
    func testCancellationAwaitsCleanupAndIdle() async throws {
        let root = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: root) }
        let helper = try executable("""
        trap '/bin/sleep 0.1; echo done > "$0.done"; exit 130' TERM
        echo ready > "$0.ready"
        while :; do /bin/sleep 0.05; done
        """, in: root)
        let client = TranscriptionClient(testExecutable: helper)
        let work = Task { try await client.run(request: .object(["operation": .string("transcribe")])) }
        for _ in 0..<100 {
            if FileManager.default.fileExists(atPath: helper.path + ".ready") { break }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertTrue(client.hasPendingWork)
        work.cancel()
        do { _ = try await work.value; XCTFail("Expected cancellation") }
        catch { XCTAssertEqual(error as? TranscriptionClientError, .cancelled) }
        XCTAssertTrue(FileManager.default.fileExists(atPath: helper.path + ".done"))
        XCTAssertFalse(client.hasPendingWork)
    }
    func testLargeStderrIsDrainedAndBounded() async throws {
        let root = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: root) }
        let helper = try executable("""
        i=0
        while [ "$i" -lt 4096 ]; do
          echo 'diagnostic diagnostic diagnostic diagnostic diagnostic diagnostic' >&2
          i=$((i + 1))
        done
        exit 2
        """, in: root)
        do {
            _ = try await TranscriptionClient(testExecutable: helper).run(request: .object([:]))
            XCTFail("Expected failure")
        } catch {
            XCTAssertLessThanOrEqual(error.localizedDescription.utf8.count, TranscriptionClient.maximumDiagnosticBytes)
            XCTAssertTrue(error.localizedDescription.hasPrefix("diagnostic"))
        }
    }
    func testResultBeforeFailedExitIsFailure() async throws {
        let root = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: root) }
        let helper = try executable("echo '{\"event\":\"result\"}'\nexit 7\n", in: root)
        do {
            _ = try await TranscriptionClient(testExecutable: helper).run(request: .object([:]))
            XCTFail("Result cannot certify a failed helper exit")
        } catch { XCTAssertTrue(error.localizedDescription.contains("7")) }
    }
    func testOversizedResultLineFailsWithoutKeepingUnboundedOutput() async throws {
        let root = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: root) }
        let helper = try executable("/usr/bin/awk 'BEGIN { for(i=0; i<33000; i++) printf \"%01024d\", 0; print \"\" }'\n", in: root)
        let client = TranscriptionClient(testExecutable: helper)
        do {
            _ = try await client.run(request: .object([:]))
            XCTFail("Expected bounded response failure")
        } catch {
            XCTAssertEqual(error as? TranscriptionClientError, .invalidResponse("The transcription helper exceeded the 32 MiB response limit."))
        }
        XCTAssertFalse(client.hasPendingWork)
    }
    func testMalformedOrRepeatedResultsFail() async throws {
        let root = try temporaryDirectory()
        defer { try? FileManager.default.removeItem(at: root) }
        for script in ["echo broken\n", "echo '{\"event\":\"result\"}'\necho '{\"event\":\"result\"}'\n"] {
            let helper = try executable(script, in: root)
            do {
                _ = try await TranscriptionClient(testExecutable: helper).run(request: .object([:]))
                XCTFail("Expected malformed response failure")
            } catch { }
        }
    }
}

final class TranscriptionDocumentTests: XCTestCase {
    private func fixture() throws -> (URL, URL) {
        let root = FileManager.default.temporaryDirectory.appendingPathComponent("ativ-document-test-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        let audio = root.appendingPathComponent("recording.wav")
        try Data("audio identity".utf8).write(to: audio)
        return (root, audio)
    }
    private var transcript: JSONValue {
        .object([
            "segments": .array([.object(["text": .string("こんにちは 🌏"), "words": .array([])])]),
            "provenance": .object(["engineID": .string("qwen"), "modelID": .string("pinned-model")]),
            "alignmentProvenance": .object(["engineID": .string("aligner"), "modelID": .string("independent-model")]),
            "futureAdditiveField": .object(["preserved": .bool(true), "largeInteger": .unsignedInteger(UInt64.max)])
        ])
    }
    func testRoundtripPreservesCanonicalPayloadAndAppearanceSeparately() async throws {
        let (root, audio) = try fixture()
        defer { try? FileManager.default.removeItem(at: root) }
        let source = try await TranscriptionSourceIdentity.fingerprint(of: audio)
        let document = TranscriptionDocument(source: source, transcript: transcript,
                                             captionPreferences: .object(["maximumWords": .number(4)]))
        let destination = root.appendingPathComponent("transcript.ativtranscript")
        try await document.save(to: destination, sourceURL: audio)
        let reopened = try await TranscriptionDocument.read(from: destination)
        XCTAssertEqual(reopened, document)
        XCTAssertEqual(reopened.transcript["futureAdditiveField"]?["preserved"], .bool(true))
    }
    func testMovedSourceMatchesAndReplacementDoesNot() async throws {
        let (root, audio) = try fixture()
        defer { try? FileManager.default.removeItem(at: root) }
        let source = try await TranscriptionSourceIdentity.fingerprint(of: audio)
        let moved = root.appendingPathComponent("moved.wav")
        try FileManager.default.moveItem(at: audio, to: moved)
        let matchesMoved = try await source.matches(moved)
        XCTAssertTrue(matchesMoved)
        try Data("other content".utf8).write(to: moved)
        let matchesReplacement = try await source.matches(moved)
        XCTAssertFalse(matchesReplacement)
    }
    func testFutureAndMalformedDocumentsAreRejectedWithoutChanges() async throws {
        let (root, _) = try fixture()
        defer { try? FileManager.default.removeItem(at: root) }
        let future = root.appendingPathComponent("future.json")
        let data = Data("{\"formatVersion\":999,\"transcript\":{}}".utf8)
        try data.write(to: future)
        do { _ = try await TranscriptionDocument.read(from: future); XCTFail("Expected future version rejection") }
        catch { XCTAssertEqual(error as? TranscriptionDocumentError, .unsupportedVersion(999)) }
        XCTAssertEqual(try Data(contentsOf: future), data)
        try Data("{\"formatVersion\":1}".utf8).write(to: future)
        do { _ = try await TranscriptionDocument.read(from: future); XCTFail("Expected malformed rejection") }
        catch { XCTAssertEqual(error as? TranscriptionDocumentError, .malformed) }
    }
    func testMalformedCaptionPreferencesAreRejectedAndLargeSafeLimitsRemainReadable() async throws {
        let (root, audio) = try fixture()
        defer { try? FileManager.default.removeItem(at: root) }
        let source = try await TranscriptionSourceIdentity.fingerprint(of: audio)
        let invalid: [JSONValue] = [
            .object(["maximumWords": .string("six")]),
            .object(["maximumCharacters": .number(0)]),
            .object(["maximumDurationSeconds": .number(-1)]),
            .object(["sourceStartSeconds": .number(3), "sourceEndSeconds": .number(2)]),
            .object(["sourceEndSeconds": .string("later")]),
            .object(["timelineStartSeconds": .null])
        ]
        for preferences in invalid {
            XCTAssertThrowsError(try TranscriptionDocument(source: source, transcript: transcript, captionPreferences: preferences).validateEnvelope())
        }
        let safe = TranscriptionDocument(source: source, transcript: transcript,
                                          captionPreferences: .object(["maximumWords": .number(1e300), "sourceEndSeconds": .null]))
        XCTAssertNoThrow(try safe.validateEnvelope())
    }
    func testSourceAliasesAndExistingDestinationsAreProtected() async throws {
        let (root, audio) = try fixture()
        defer { try? FileManager.default.removeItem(at: root) }
        let alias = root.appendingPathComponent("symlink.wav")
        let hardLink = root.appendingPathComponent("hardlink.wav")
        try FileManager.default.createSymbolicLink(at: alias, withDestinationURL: audio)
        try FileManager.default.linkItem(at: audio, to: hardLink)
        let sourceData = try Data(contentsOf: audio)
        for url in [audio, alias, hardLink] {
            do {
                try await TranscriptionDocument.write(data: Data("subtitle".utf8), to: url, sourceURL: audio, replacingExisting: true)
                XCTFail("Expected alias protection")
            } catch { XCTAssertEqual(error as? TranscriptionDocumentError, .destinationIsSource) }
        }
        XCTAssertEqual(try Data(contentsOf: audio), sourceData)
        let artwork = root.appendingPathComponent("artwork.png")
        try Data("image".utf8).write(to: artwork)
        do {
            try await TranscriptionDocument.write(data: Data("subtitle".utf8), to: artwork, sourceURL: audio,
                                                   replacingExisting: true, protectedURLs: [artwork])
            XCTFail("Expected image source protection")
        } catch { XCTAssertEqual(error as? TranscriptionDocumentError, .destinationIsSource) }
        XCTAssertEqual(try Data(contentsOf: artwork), Data("image".utf8))
        let existing = root.appendingPathComponent("existing.srt")
        try Data("previous".utf8).write(to: existing)
        do {
            try await TranscriptionDocument.write(data: Data("new".utf8), to: existing, sourceURL: audio)
            XCTFail("Expected explicit replace requirement")
        } catch { XCTAssertEqual(error as? TranscriptionDocumentError, .destinationExists) }
        XCTAssertEqual(try Data(contentsOf: existing), Data("previous".utf8))
        try await TranscriptionDocument.write(data: Data("new".utf8), to: existing, sourceURL: audio, replacingExisting: true)
        XCTAssertEqual(try Data(contentsOf: existing), Data("new".utf8))
    }
}
