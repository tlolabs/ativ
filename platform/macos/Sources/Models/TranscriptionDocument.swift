// SPDX-License-Identifier: GPL-3.0-or-later
import CryptoKit
import Darwin
import Foundation

enum TranscriptionDocumentError: Error, LocalizedError, Equatable {
    case unsupportedVersion(Int), malformed, sourceChanged, destinationIsSource, destinationExists, oversized
    var errorDescription: String? {
        switch self {
        case .unsupportedVersion(let version): return "This transcript uses unsupported document version \(version). Update ATIV before opening it."
        case .malformed: return "The transcript document is malformed or incomplete."
        case .sourceChanged: return "The audio changed while being read. Select the source again."
        case .destinationIsSource: return "A transcript or subtitle cannot replace its source audio. Choose another destination."
        case .destinationExists: return "A file already exists at this destination. Choose Replace explicitly to overwrite it."
        case .oversized: return "This transcript exceeds the supported 32 MiB document size."
        }
    }
}

/// Content identity survives a move; its stored path is a hint, never proof of identity.
struct TranscriptionSourceIdentity: Codable, Equatable, Sendable {
    let sha256: String
    let byteCount: UInt64
    let originalPath: String?

    static func fingerprint(of url: URL) async throws -> TranscriptionSourceIdentity {
        try await transcriptionBackground { try fingerprintSynchronously(of: url) }
    }
    func matches(_ url: URL) async throws -> Bool {
        let candidate = try await Self.fingerprint(of: url)
        return sha256 == candidate.sha256 && byteCount == candidate.byteCount
    }
    private static func fingerprintSynchronously(of url: URL) throws -> TranscriptionSourceIdentity {
        guard url.isFileURL else { throw TranscriptionDocumentError.malformed }
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        var before = stat()
        guard fstat(handle.fileDescriptor, &before) == 0,
              before.st_mode & mode_t(S_IFMT) == mode_t(S_IFREG), before.st_size >= 0 else {
            throw TranscriptionDocumentError.malformed
        }
        var digest = SHA256()
        var count: UInt64 = 0
        while true {
            try Task.checkCancellation()
            let data = try handle.read(upToCount: 1024 * 1024) ?? Data()
            if data.isEmpty { break }
            digest.update(data: data)
            count += UInt64(data.count)
        }
        var after = stat(), current = stat()
        guard fstat(handle.fileDescriptor, &after) == 0, stat(url.path, &current) == 0,
              before.st_dev == after.st_dev, before.st_ino == after.st_ino,
              current.st_dev == after.st_dev, current.st_ino == after.st_ino,
              before.st_size == after.st_size, count == UInt64(after.st_size),
              before.st_mtimespec.tv_sec == after.st_mtimespec.tv_sec,
              before.st_mtimespec.tv_nsec == after.st_mtimespec.tv_nsec,
              before.st_ctimespec.tv_sec == after.st_ctimespec.tv_sec,
              before.st_ctimespec.tv_nsec == after.st_ctimespec.tv_nsec else {
            throw TranscriptionDocumentError.sourceChanged
        }
        return .init(sha256: digest.finalize().map { String(format: "%02x", $0) }.joined(),
                     byteCount: count, originalPath: url.path)
    }
}

/// The canonical Core transcript is retained intact, including unknown additive fields.
/// Appearance/grouping preferences have their own envelope, outside recognition provenance.
struct TranscriptionDocument: Codable, Equatable, Sendable {
    static let currentVersion = 1
    static let maximumBytes = 32 * 1024 * 1024
    let formatVersion: Int
    let source: TranscriptionSourceIdentity
    let transcript: JSONValue
    var captionPreferences: JSONValue

    init(source: TranscriptionSourceIdentity, transcript: JSONValue, captionPreferences: JSONValue = .object([:])) {
        formatVersion = Self.currentVersion
        self.source = source
        self.transcript = transcript
        self.captionPreferences = captionPreferences
    }

    func validateEnvelope() throws {
        guard formatVersion == Self.currentVersion else { throw TranscriptionDocumentError.unsupportedVersion(formatVersion) }
        guard source.sha256.count == 64, source.sha256.allSatisfy({ "0123456789abcdef".contains($0) }),
              source.originalPath == nil || source.originalPath!.hasPrefix("/"),
              transcript["segments"]?.arrayValue != nil,
              transcript["provenance"]?["modelID"]?.stringValue != nil,
              transcript["provenance"]?["engineID"]?.stringValue != nil,
              captionPreferences.objectValue != nil else { throw TranscriptionDocumentError.malformed }
        func numericPreference(_ key: String, default fallback: Double, minimum: Double, inclusive: Bool = true) throws -> Double {
            guard let value = captionPreferences[key] else { return fallback }
            guard let number = value.doubleValue, number.isFinite,
                  inclusive ? number >= minimum : number > minimum else { throw TranscriptionDocumentError.malformed }
            return number
        }
        _ = try numericPreference("maximumWords", default: 6, minimum: 0, inclusive: false)
        _ = try numericPreference("maximumCharacters", default: 42, minimum: 0, inclusive: false)
        _ = try numericPreference("maximumDurationSeconds", default: 3, minimum: 0, inclusive: false)
        _ = try numericPreference("maximumPauseSeconds", default: 0.6, minimum: 0)
        let sourceStart = try numericPreference("sourceStartSeconds", default: 0, minimum: 0)
        _ = try numericPreference("timelineStartSeconds", default: 0, minimum: 0)
        if let end = captionPreferences["sourceEndSeconds"], end != .null {
            _ = try numericPreference("sourceEndSeconds", default: sourceStart, minimum: sourceStart)
        }
        // Full transcript/timestamp validation is performed by the shared helper's validate operation.
        // This lightweight check permits inspecting/saving existing records on unsupported Macs.
        for segment in transcript["segments"]!.arrayValue! {
            guard segment["text"]?.stringValue != nil else { throw TranscriptionDocumentError.malformed }
        }
    }

    static func read(from url: URL) async throws -> TranscriptionDocument {
        try await transcriptionBackground {
            let data = try readBounded(from: url)
            let header = try JSONDecoder().decode(JSONValue.self, from: data)
            guard let version = header["formatVersion"]?.doubleValue, version.isFinite,
                  version.rounded() == version, version >= Double(Int.min), version < Double(Int.max) else {
                throw TranscriptionDocumentError.malformed
            }
            guard version == Double(currentVersion) else { throw TranscriptionDocumentError.unsupportedVersion(Int(version)) }
            let document: TranscriptionDocument
            do { document = try JSONDecoder().decode(TranscriptionDocument.self, from: data) }
            catch { throw TranscriptionDocumentError.malformed }
            try document.validateEnvelope()
            return document
        }
    }
    func save(to url: URL, sourceURL: URL, replacingExisting: Bool = false, protectedURLs: [URL] = []) async throws {
        try validateEnvelope()
        let data = try await transcriptionBackground {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
            return try encoder.encode(self)
        }
        try await Self.write(data: data, to: url, sourceURL: sourceURL, replacingExisting: replacingExisting, protectedURLs: protectedURLs)
    }
    static func write(data: Data, to url: URL, sourceURL: URL, replacingExisting: Bool = false, protectedURLs: [URL] = []) async throws {
        try await transcriptionBackground {
            guard data.count <= maximumBytes else { throw TranscriptionDocumentError.oversized }
            guard url.isFileURL, sourceURL.isFileURL else { throw TranscriptionDocumentError.malformed }
            guard !(protectedURLs + [sourceURL]).contains(where: { sameFile(url, $0) }) else { throw TranscriptionDocumentError.destinationIsSource }
            let parent = url.deletingLastPathComponent()
            let staging = parent.appendingPathComponent(".ativ-transcript-\(UUID().uuidString).tmp")
            let fd = open(staging.path, O_WRONLY | O_CREAT | O_EXCL, S_IRUSR | S_IWUSR)
            guard fd >= 0 else { throw CocoaError(.fileWriteUnknown) }
            let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
            defer { try? handle.close(); try? FileManager.default.removeItem(at: staging) }
            try handle.write(contentsOf: data)
            try handle.synchronize()
            try handle.close()
            try Task.checkCancellation()
            guard !(protectedURLs + [sourceURL]).contains(where: { sameFile(url, $0) }) else { throw TranscriptionDocumentError.destinationIsSource }
            if replacingExisting {
                guard rename(staging.path, url.path) == 0 else { throw CocoaError(.fileWriteUnknown) }
            } else {
                // link(2) publishes atomically only if absent; unlike rename, it never silently replaces.
                guard link(staging.path, url.path) == 0 else {
                    if errno == EEXIST { throw TranscriptionDocumentError.destinationExists }
                    throw CocoaError(.fileWriteUnknown)
                }
            }
        }
    }
    private static func readBounded(from url: URL) throws -> Data {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let data = try handle.read(upToCount: maximumBytes + 1) ?? Data()
        guard data.count <= maximumBytes else { throw TranscriptionDocumentError.oversized }
        return data
    }
    static func sameFile(_ lhs: URL, _ rhs: URL) -> Bool {
        if lhs.standardizedFileURL.resolvingSymlinksInPath() == rhs.standardizedFileURL.resolvingSymlinksInPath() { return true }
        var a = stat(), b = stat()
        return stat(lhs.path, &a) == 0 && stat(rhs.path, &b) == 0 && a.st_dev == b.st_dev && a.st_ino == b.st_ino
    }
}

/// Cancellation propagates to background file operations before any publication.
private func transcriptionBackground<T: Sendable>(_ operation: @escaping @Sendable () throws -> T) async throws -> T {
    let work = Task.detached(priority: .userInitiated) {
        try Task.checkCancellation()
        return try operation()
    }
    return try await withTaskCancellationHandler(operation: { try await work.value }, onCancel: { work.cancel() })
}
