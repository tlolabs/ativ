// SPDX-License-Identifier: GPL-3.0-or-later
import Foundation

/// A lossless wire envelope: the macOS 13 app does not link macOS 14 inference libraries.
indirect enum JSONValue: Codable, Equatable, Sendable {
    case object([String: JSONValue]), array([JSONValue]), string(String), number(Double), integer(Int64), unsignedInteger(UInt64), bool(Bool), null

    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer()
        if value.decodeNil() { self = .null }
        else if let item = try? value.decode(Bool.self) { self = .bool(item) }
        else if let item = try? value.decode(String.self) { self = .string(item) }
        else if let item = try? value.decode(Int64.self) { self = .integer(item) }
        else if let item = try? value.decode(UInt64.self) { self = .unsignedInteger(item) }
        else if let item = try? value.decode(Double.self) { self = .number(item) }
        else if let item = try? value.decode([JSONValue].self) { self = .array(item) }
        else { self = .object(try value.decode([String: JSONValue].self)) }
    }
    func encode(to encoder: Encoder) throws {
        var value = encoder.singleValueContainer()
        switch self {
        case .object(let item): try value.encode(item)
        case .array(let item): try value.encode(item)
        case .string(let item): try value.encode(item)
        case .number(let item): try value.encode(item)
        case .integer(let item): try value.encode(item)
        case .unsignedInteger(let item): try value.encode(item)
        case .bool(let item): try value.encode(item)
        case .null: try value.encodeNil()
        }
    }
    subscript(_ key: String) -> JSONValue? { objectValue?[key] }
    var objectValue: [String: JSONValue]? { if case .object(let item) = self { return item }; return nil }
    var arrayValue: [JSONValue]? { if case .array(let item) = self { return item }; return nil }
    var stringValue: String? { if case .string(let item) = self { return item }; return nil }
    var doubleValue: Double? {
        switch self {
        case .number(let item): return item
        case .integer(let item): return Double(item)
        case .unsignedInteger(let item): return Double(item)
        default: return nil
        }
    }
    static func == (lhs: JSONValue, rhs: JSONValue) -> Bool {
        switch (lhs, rhs) {
        case (.object(let a), .object(let b)): return a == b
        case (.array(let a), .array(let b)): return a == b
        case (.string(let a), .string(let b)): return a == b
        case (.bool(let a), .bool(let b)): return a == b
        case (.null, .null): return true
        case (.number(let a), .number(let b)): return a == b
        case (.integer(let a), .integer(let b)): return a == b
        case (.unsignedInteger(let a), .unsignedInteger(let b)): return a == b
        case (.integer(let a), .unsignedInteger(let b)), (.unsignedInteger(let b), .integer(let a)): return UInt64(exactly: a) == b
        case (.number(let a), .integer(let b)), (.integer(let b), .number(let a)): return Int64(exactly: a) == b
        case (.number(let a), .unsignedInteger(let b)), (.unsignedInteger(let b), .number(let a)): return UInt64(exactly: a) == b
        default: return false
        }
    }
    var boolValue: Bool? { if case .bool(let item) = self { return item }; return nil }
}

struct TranscriptionCapability: Equatable, Sendable {
    let isSupported: Bool
    let reason: String
}

enum TranscriptionClientError: Error, LocalizedError, Equatable {
    case unavailable(String), invalidResponse(String), failed(String), cancelled
    var errorDescription: String? {
        switch self {
        case .unavailable(let reason), .invalidResponse(let reason), .failed(let reason): return reason
        case .cancelled: return "The transcription operation was cancelled."
        }
    }
}

/// Cancellation never reports completion while inference still holds a model lease.
final class TranscriptionClient: @unchecked Sendable {
    private let helperOverride: URL?
    private let worker = DispatchQueue(label: "com.tlolabs.ativ.transcription", qos: .userInitiated)
    private let lock = NSLock()
    private var operations: [UUID: TranscriptionProcessOperation] = [:]
    static let maximumLineBytes = 32 * 1024 * 1024
    static let maximumDiagnosticBytes = 64 * 1024

    init() { helperOverride = nil }
    /// Explicit dependency injection for process tests; production has no PATH/cache fallback.
    init(testExecutable: URL) { helperOverride = testExecutable }

    private var helperURL: URL {
        helperOverride ?? Self.packagedHelperURL(in: Bundle.main.bundleURL)
    }
    static func capability(osMajorVersion: Int, isAppleSilicon: Bool, helperExists: Bool) -> TranscriptionCapability {
        guard isAppleSilicon else {
            return .init(isSupported: false, reason: "Local transcription requires an Apple silicon Mac. Video creation remains available.")
        }
        guard osMajorVersion >= 14 else {
            return .init(isSupported: false, reason: "Local transcription requires macOS 14 or later. Video creation remains available.")
        }
        guard helperExists else {
            return .init(isSupported: false, reason: "The transcription helper or its resources are missing. Install a complete Apple silicon ATIV build.")
        }
        return .init(isSupported: true, reason: "Local transcription runs on this Mac using verified models shared with other AVID applications.")
    }
    var capability: TranscriptionCapability {
        if helperOverride != nil { return .init(isSupported: true, reason: "Injected test helper") }
        #if arch(arm64)
        let silicon = true
        #else
        let silicon = false
        #endif
        return Self.capability(osMajorVersion: ProcessInfo.processInfo.operatingSystemVersion.majorVersion,
                               isAppleSilicon: silicon,
                               helperExists: Self.packagedHelperExists(at: helperURL))
    }
    static func packagedHelperURL(in application: URL) -> URL {
        application.appendingPathComponent("Contents/Helpers/ATIVTranscriptionHelper.app/Contents/MacOS/ATIVTranscriptionHelper")
    }
    static func packagedHelperExists(at executable: URL) -> Bool {
        let files = FileManager.default
        let contents = executable.deletingLastPathComponent().deletingLastPathComponent()
        let directory = contents.appendingPathComponent("Resources")
        // The manifest belongs to the outer app so it can hash the finalized nested helper signature.
        let outerContents = contents.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let manifest = outerContents.appendingPathComponent("Resources/transcription-package.json")
        func hasResource(_ bundle: String, _ file: String) -> Bool {
            ["Contents/Resources/", ""].contains { prefix in
                files.fileExists(atPath: directory.appendingPathComponent(bundle + "/" + prefix + file).path)
            }
        }
        // Package validation checks actual Mach-O imports for toolchain-dependent dylibs.
        return files.isExecutableFile(atPath: executable.path)
            && files.fileExists(atPath: manifest.path)
            && hasResource("AVIDTranscription_AVIDTranscription.bundle", "models.json")
            && hasResource("mlx-swift_Cmlx.bundle", "default.metallib")
    }
    var hasPendingWork: Bool { lock.withLock { !operations.isEmpty } }
    func whenIdle(completion: @escaping () -> Void) { worker.async(execute: completion) }
    func cancelAll() {
        let pending = lock.withLock { Array(operations.values) }
        pending.forEach { $0.cancel() }
    }

    func run(request: JSONValue, progress: @escaping @Sendable (JSONValue) -> Void = { _ in }) async throws -> JSONValue {
        guard capability.isSupported else { throw TranscriptionClientError.unavailable(capability.reason) }
        let operation = TranscriptionProcessOperation()
        let id = UUID()
        lock.withLock { operations[id] = operation }
        return try await withTaskCancellationHandler(operation: {
            try await withCheckedThrowingContinuation { continuation in
                worker.async {
                    let result: Result<JSONValue, Error>
                    do { result = .success(try operation.perform(executable: self.helperURL, request: request, progress: progress)) }
                    catch { result = .failure(error) }
                    self.lock.withLock { _ = self.operations.removeValue(forKey: id) }
                    continuation.resume(with: result)
                }
            }
        }, onCancel: { operation.cancel() })
    }
}

private final class TranscriptionProcessOperation: @unchecked Sendable {
    private let lock = NSLock()
    private var cancelled = false
    private var process: Process?

    func cancel() {
        lock.withLock {
            cancelled = true
            // Serialize termination with launch/exit so a reused pid cannot be signalled.
            if let process, process.isRunning { process.terminate() }
        }
    }
    private func checkCancellation() throws {
        if lock.withLock({ cancelled }) { throw TranscriptionClientError.cancelled }
    }

    func perform(executable: URL, request: JSONValue, progress: @escaping @Sendable (JSONValue) -> Void) throws -> JSONValue {
        try checkCancellation()
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("ativ-transcription-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        defer { try? FileManager.default.removeItem(at: directory) }
        let requestURL = directory.appendingPathComponent("request.json")
        let encoded = try JSONEncoder().encode(request)
        guard encoded.count <= TranscriptionClient.maximumLineBytes else {
            throw TranscriptionClientError.failed("The transcript exceeds the supported 32 MiB request size.")
        }
        try encoded.write(to: requestURL, options: [.withoutOverwriting])
        let child = Process()
        child.executableURL = executable
        child.arguments = ["--request", requestURL.path]
        child.currentDirectoryURL = executable.deletingLastPathComponent()
        let stdout = Pipe(), stderr = Pipe()
        child.standardOutput = stdout
        child.standardError = stderr
        child.standardInput = FileHandle.nullDevice
        try lock.withLock {
            guard !cancelled else { throw TranscriptionClientError.cancelled }
            try child.run()
            process = child
        }
        // The parent must close its inherited writing ends before EOF can be observed.
        try? stdout.fileHandleForWriting.close()
        try? stderr.fileHandleForWriting.close()
        let diagnostics = TranscriptionDiagnostics()
        let drain = DispatchGroup()
        drain.enter()
        DispatchQueue.global(qos: .utility).async {
            defer { drain.leave() }
            while true {
                let data = stderr.fileHandleForReading.readData(ofLength: 16 * 1024)
                if data.isEmpty { break }
                diagnostics.append(data)
            }
        }
        var pending = Data()
        var result: JSONValue?
        var responseError: Error?
        var discardLine = false
        func consumeLine(_ line: Data) {
            guard responseError == nil, !line.isEmpty else { return }
            do {
                let event = try JSONDecoder().decode(JSONValue.self, from: line)
                switch event["event"]?.stringValue {
                case "progress": progress(event)
                case "result":
                    guard result == nil else { throw TranscriptionClientError.invalidResponse("The transcription helper returned multiple results.") }
                    result = event
                case "error": responseError = TranscriptionClientError.failed(event["message"]?.stringValue ?? "The transcription helper failed.")
                default: throw TranscriptionClientError.invalidResponse("The transcription helper returned an unknown event.")
                }
            } catch { responseError = error }
        }
        while true {
            let chunk = stdout.fileHandleForReading.readData(ofLength: 16 * 1024)
            if chunk.isEmpty { break }
            var start = chunk.startIndex
            while start < chunk.endIndex {
                let newline = chunk[start...].firstIndex(of: 10)
                let end = newline ?? chunk.endIndex
                if !discardLine {
                    let bytes = chunk[start..<end]
                    if bytes.count <= TranscriptionClient.maximumLineBytes - pending.count {
                        pending.append(bytes)
                    } else {
                        pending.removeAll(keepingCapacity: false)
                        discardLine = true
                        responseError = TranscriptionClientError.invalidResponse("The transcription helper exceeded the 32 MiB response limit.")
                        lock.withLock { if child.isRunning { child.terminate() } }
                    }
                }
                guard let newline else { break }
                if !discardLine { consumeLine(pending) }
                pending.removeAll(keepingCapacity: true)
                discardLine = false
                start = chunk.index(after: newline)
            }
        }
        if !discardLine { consumeLine(pending) }
        child.waitUntilExit()
        drain.wait()
        lock.withLock { process = nil }
        try? stdout.fileHandleForReading.close()
        try? stderr.fileHandleForReading.close()
        try checkCancellation()
        if let responseError { throw responseError }
        guard child.terminationReason == .exit, child.terminationStatus == 0 else {
            let detail = diagnostics.text
            throw TranscriptionClientError.failed(detail.isEmpty ? "The transcription helper exited with status \(child.terminationStatus)." : detail)
        }
        guard let result else { throw TranscriptionClientError.invalidResponse("The transcription helper returned no result.") }
        return result
    }
}

private final class TranscriptionDiagnostics: @unchecked Sendable {
    private let lock = NSLock()
    private var buffer = Data()
    func append(_ data: Data) {
        lock.withLock {
            let remaining = TranscriptionClient.maximumDiagnosticBytes - buffer.count
            if remaining > 0 { buffer.append(data.prefix(remaining)) }
        }
    }
    var text: String { lock.withLock { String(decoding: buffer, as: UTF8.self) } }
}
