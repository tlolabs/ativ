import AVIDTranscription
import Foundation

/// Version 1 is request-per-process. No audio bytes cross the JSON boundary.
/// Transcript JSON is always decoded by the canonical shared Core contracts.
public struct HelperRequest: Codable, Sendable {
    public let operation: String
    public let modelID: String?
    public let audioPath: String?
    public let language: String?
    public let transcript: Transcript?
    public let sourceOffset: Double?
    public let localPath: String?
    public let cachePath: String?
    public let segmentIndex: Int?
    public let text: String?
    public let edits: [TranscriptEditInput]?
    public let captionOptions: CaptionOptionsInput?
    public let captionWindow: CaptionWindowInput?

    public static func read(from url: URL) throws -> Self {
        let size = try url.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? 0
        guard size <= 64 * 1024 * 1024 else { throw BridgeError.invalid("Request exceeds 64 MiB.") }
        return try JSONDecoder().decode(Self.self, from: Data(contentsOf: url))
    }

    public func requiredModelID() throws -> String {
        guard let modelID, !modelID.isEmpty else { throw BridgeError.invalid("A model ID is required.") }
        return modelID
    }

    public func requiredTranscript() throws -> Transcript {
        guard let transcript else { throw BridgeError.invalid("A canonical transcript is required.") }
        return transcript
    }

    public func requiredLocalURL(_ value: String?, label: String) throws -> URL {
        guard let value, value.hasPrefix("/"), !value.contains("\0") else {
            throw BridgeError.invalid("\(label) must be an absolute local path.")
        }
        return URL(fileURLWithPath: value).standardizedFileURL
    }

    public func validatedSourceOffset() throws -> Double {
        let result = sourceOffset ?? 0
        guard result.isFinite, result >= 0 else { throw BridgeError.invalid("Source offset must be finite and nonnegative.") }
        return result
    }

    public func editingTranscript() throws -> Transcript {
        let original = try requiredTranscript()
        guard let edits else {
            guard let segmentIndex, let text else { throw BridgeError.invalid("Segment index and replacement text are required.") }
            return try original.correctingSegment(at: segmentIndex, text: text)
        }
        guard segmentIndex == nil, text == nil else {
            throw BridgeError.invalid("Choose either a batch of edits or one segment edit.")
        }
        var indices = Set<Int>()
        for edit in edits {
            guard original.segments.indices.contains(edit.segmentIndex), indices.insert(edit.segmentIndex).inserted else {
                throw BridgeError.invalid("Batch edit indices must be unique and in range.")
            }
        }
        guard !edits.isEmpty else { return original }
        var updated = original.segments
        for edit in edits {
            try Task.checkCancellation()
            updated[edit.segmentIndex] = try updated[edit.segmentIndex].replacingText(with: edit.text)
        }
        try Task.checkCancellation()
        return try Transcript(segments: updated, language: original.language, provenance: original.provenance)
    }

    public func captionResult() throws -> HelperEvent {
        let cues = try CaptionBuilder.cues(from: requiredTranscript(),
            options: captionOptions?.value ?? CaptionOptions(),
            window: captionWindow?.value ?? CaptionWindow())
        return HelperEvent(cues: cues, srt: try CaptionExporter.srt(cues), webVTT: try CaptionExporter.webVTT(cues))
    }
}

public struct TranscriptEditInput: Codable, Sendable {
    public let segmentIndex: Int
    public let text: String
}

public struct CaptionOptionsInput: Codable, Sendable {
    public let maximumCharacters: Int?
    public let maximumWords: Int?
    public let maximumDurationSeconds: Double?
    public let maximumPauseSeconds: Double?
    public var value: CaptionOptions {
        CaptionOptions(maximumCharacters: maximumCharacters ?? 42, maximumWords: maximumWords ?? 6,
            maximumDurationSeconds: maximumDurationSeconds ?? 3, maximumPauseSeconds: maximumPauseSeconds ?? 0.6)
    }
}

public struct CaptionWindowInput: Codable, Sendable {
    public let sourceStartSeconds: Double?
    public let sourceEndSeconds: Double?
    public let timelineStartSeconds: Double?
    public var value: CaptionWindow {
        CaptionWindow(sourceStartSeconds: sourceStartSeconds ?? 0, sourceEndSeconds: sourceEndSeconds,
            timelineStartSeconds: timelineStartSeconds ?? 0)
    }
}

public struct ModelSummary: Codable, Sendable {
    public let id: String
    public let displayName: String
    public let role: String
    public let engine: String
    public let revision: String
    public let installationID: String
    public let downloadBytes: Int64
    public let diskBytes: Int64
    public let partialBytes: Int64
    public let installed: Bool
    public let verificationState: String
    public let license: ModelLicense
    public let recognitionLanguages: [String]
    public let timingLanguages: [String]

    public init(descriptor: ModelDescriptor, root: URL, installed: Bool) {
        id = descriptor.id; displayName = descriptor.displayName; role = descriptor.role.rawValue
        engine = descriptor.engine.rawValue; revision = descriptor.revision; installationID = descriptor.installationID
        downloadBytes = descriptor.downloadSizeBytes; self.installed = installed; verificationState = "notChecked"
        license = descriptor.license; recognitionLanguages = descriptor.recognitionLanguages; timingLanguages = descriptor.timingLanguages
        let parent = root.appendingPathComponent(descriptor.id, isDirectory: true)
        diskBytes = Self.listedBytes(descriptor, at: parent.appendingPathComponent(descriptor.installationID, isDirectory: true))
        partialBytes = Self.listedBytes(descriptor, at: parent.appendingPathComponent(".\(descriptor.installationID).partial", isDirectory: true))
    }

    // Display actual listed bytes without following symlinks or scanning unrecognized directories.
    // Presence is deliberately distinct from integrity; verify and every inference check all hashes.
    private static func listedBytes(_ model: ModelDescriptor, at directory: URL) -> Int64 {
        model.artifacts.reduce(0) { total, artifact in
            let file = directory.appendingPathComponent(artifact.path)
            guard file.resolvingSymlinksInPath().path == file.standardizedFileURL.path,
                  let attributes = try? FileManager.default.attributesOfItem(atPath: file.path),
                  attributes[.type] as? FileAttributeType == .typeRegular,
                  let size = attributes[.size] as? NSNumber, size.int64Value >= 0 else { return total }
            let sum = total.addingReportingOverflow(size.int64Value)
            return sum.overflow ? total : sum.partialValue
        }
    }
}

public struct HelperEvent: Codable, Sendable {
    public let event: String
    public let protocolVersion: Int
    public let message: String?
    public let fraction: Double?
    public let models: [ModelSummary]?
    public let defaultModelID: String?
    public let cachePath: String?
    public let transcript: Transcript?
    public let cues: [CaptionCue]?
    public let srt: String?
    public let webVTT: String?

    public init(event: String = "result", message: String? = nil, fraction: Double? = nil,
                models: [ModelSummary]? = nil, defaultModelID: String? = nil, cachePath: String? = nil,
                transcript: Transcript? = nil, cues: [CaptionCue]? = nil, srt: String? = nil, webVTT: String? = nil) {
        self.event = event; protocolVersion = 1; self.message = message
        self.fraction = fraction.flatMap { $0.isFinite ? min(1, max(0, $0)) : nil }
        self.models = models; self.defaultModelID = defaultModelID; self.cachePath = cachePath
        self.transcript = transcript; self.cues = cues; self.srt = srt; self.webVTT = webVTT
    }
}

public enum BridgeError: Error, LocalizedError, Sendable {
    case invalid(String)
    public var errorDescription: String? { switch self { case .invalid(let value): value } }
}
