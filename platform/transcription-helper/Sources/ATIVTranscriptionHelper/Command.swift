import AVIDTranscription
import AVIDTranscriptionEngines
import Darwin
import Dispatch
import Foundation
import TranscriptionBridge

/// The original stdout descriptor is reserved for protocol messages. SDK logging
/// goes to stderr, which the parent drains independently with a bounded tail.
private final class EventWriter: @unchecked Sendable {
    private let output: FileHandle
    private let lock = NSLock()
    private var lastProgress = Date.distantPast

    init() throws {
        let protocolDescriptor = dup(STDOUT_FILENO)
        guard protocolDescriptor >= 0, dup2(STDERR_FILENO, STDOUT_FILENO) >= 0 else {
            throw BridgeError.invalid("Cannot establish transcription protocol output.")
        }
        output = FileHandle(fileDescriptor: protocolDescriptor, closeOnDealloc: true)
    }

    func send(_ value: HelperEvent) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        var data = try encoder.encode(value)
        guard data.count < 15 * 1024 * 1024 else {
            throw BridgeError.invalid("Transcript result exceeds the 15 MiB helper response limit. Split the recording into shorter sections.")
        }
        data.append(10)
        lock.lock()
        defer { lock.unlock() }
        try output.write(contentsOf: data)
    }

    func progress(_ message: String, fraction: Double?) {
        // Hashing/download callbacks can be extremely frequent. Keep the pipe and
        // main actor responsive without losing the explicit final result/error.
        lock.lock()
        let now = Date()
        guard now.timeIntervalSince(lastProgress) >= 0.1 || fraction == 1 else { lock.unlock(); return }
        lastProgress = now
        lock.unlock()
        try? send(HelperEvent(event: "progress", message: String(message.prefix(2048)), fraction: fraction))
    }
}

@main
struct Command {
    static func main() async {
        let writer: EventWriter
        do { writer = try EventWriter() }
        catch { FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8)); exit(1) }

        signal(SIGINT, SIG_IGN)
        signal(SIGTERM, SIG_IGN)
        let operation = Task.detached { try await execute(Array(CommandLine.arguments.dropFirst()), writer: writer) }
        let signals = [SIGINT, SIGTERM].map { number in
            let source = DispatchSource.makeSignalSource(signal: number, queue: .global())
            source.setEventHandler { operation.cancel() }
            source.resume()
            return source
        }
        defer { signals.forEach { $0.cancel() } }
        do {
            let result = try await operation.value
            try Task.checkCancellation()
            try writer.send(result)
        } catch is CancellationError {
            try? writer.send(HelperEvent(event: "error", message: "Cancelled. Any active model operation has finished cleanup."))
            exit(130)
        } catch {
            try? writer.send(HelperEvent(event: "error", message: String(error.localizedDescription.prefix(8192))))
            exit(1)
        }
    }

    private static func execute(_ arguments: [String], writer: EventWriter) async throws -> HelperEvent {
        #if !arch(arm64)
        throw BridgeError.invalid("Local transcription requires an Apple silicon Mac.")
        #else
        guard arguments.count == 2, arguments[0] == "--request" else {
            throw BridgeError.invalid("Usage: ATIVTranscriptionHelper --request /absolute/request.json")
        }
        guard arguments[1].hasPrefix("/") else { throw BridgeError.invalid("Request path must be absolute.") }
        let request = try HelperRequest.read(from: URL(fileURLWithPath: arguments[1]))
        try Task.checkCancellation()
        switch request.operation {
        case "validate": return HelperEvent(transcript: try request.requiredTranscript())
        case "edit": return HelperEvent(transcript: try request.editingTranscript())
        case "captions": return try request.captionResult()
        default: break
        }

        let catalog = try ModelCatalog.bundled()
        let root = try request.cachePath.map { try request.requiredLocalURL($0, label: "Cache") } ?? ModelStore.defaultDirectory
        let store = try ModelStore(catalog: catalog, rootDirectory: root)
        let reportModel: ModelProgressHandler = { value in
            writer.progress("\(value.phase.rawValue): \(value.artifactPath ?? value.modelID)", fraction: value.fraction)
        }
        let reportInference: @Sendable (TranscriptionProgress) -> Void = { value in
            writer.progress(value.stage, fraction: value.fraction)
        }

        switch request.operation {
        case "catalog":
            var models: [ModelSummary] = []
            for model in catalog.models {
                try Task.checkCancellation()
                models.append(ModelSummary(descriptor: model, root: root, installed: try await store.isPresent(id: model.id)))
            }
            return HelperEvent(models: models, defaultModelID: catalog.defaultModelID, cachePath: root.path)
        case "install":
            let installed = try await store.install(id: request.requiredModelID(), progress: reportModel)
            try Task.checkCancellation()
            return HelperEvent(message: "Installed and verified \(installed.descriptor.displayName).")
        case "verify":
            let installed = try await store.installedModel(id: request.requiredModelID(), progress: reportModel)
            try Task.checkCancellation()
            return HelperEvent(message: "All files verified for \(installed.descriptor.displayName).")
        case "import":
            let installed = try await store.importModel(id: request.requiredModelID(),
                from: request.requiredLocalURL(request.localPath, label: "Import folder"), progress: reportModel)
            try Task.checkCancellation()
            return HelperEvent(message: "Imported and verified \(installed.descriptor.displayName). Original folder retained.")
        case "remove":
            try await store.remove(id: request.requiredModelID())
            return HelperEvent(message: "Removed the selected model’s managed installations and partial downloads.")
        case "transcribe":
            let id = request.modelID ?? catalog.defaultModelID
            let descriptor = try catalog.model(id: id)
            guard descriptor.role == .recognizer else { throw BridgeError.invalid("Select a recognition model.") }
            let audio = try request.requiredLocalURL(request.audioPath, label: "Audio")
            let offset = try request.validatedSourceOffset()
            let provider: any TranscriptionProvider
            switch descriptor.engine {
            case .whisperKit: provider = WhisperKitProvider()
            case .fluidAudio: provider = FluidAudioProvider()
            case .mlx: provider = QwenASRProvider()
            }
            writer.progress("Verifying installed files before local recognition", fraction: nil)
            let transcript = try await store.withInstalledModel(id: id) { installation in
                try await provider.transcribe(RecognitionRequest(audioURL: audio, modelID: id,
                    modelDirectory: installation.directory, language: request.language, sourceStartSeconds: offset),
                    progress: reportInference)
            }
            try Task.checkCancellation()
            return HelperEvent(transcript: transcript)
        case "align":
            let id = request.modelID ?? "qwen3-forced-aligner-0.6b-4bit"
            let descriptor = try catalog.model(id: id)
            guard descriptor.role == .aligner, descriptor.engine == .mlx else {
                throw BridgeError.invalid("Select the supported Qwen alignment model.")
            }
            let transcript = try request.requiredTranscript()
            let language = request.language ?? transcript.language
            guard let language, !language.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
                throw BridgeError.invalid("Select a language to realign a transcript without detected language metadata.")
            }
            let audio = try request.requiredLocalURL(request.audioPath, label: "Audio")
            let offset = try request.validatedSourceOffset()
            writer.progress("Verifying installed files before local alignment", fraction: nil)
            let result = try await store.withInstalledModel(id: id) { installation in
                try await QwenAlignmentProvider().align(AlignmentRequest(audioURL: audio, modelID: id,
                    modelDirectory: installation.directory, transcript: transcript, language: language,
                    sourceStartSeconds: offset), progress: reportInference)
            }
            try Task.checkCancellation()
            return HelperEvent(transcript: result)
        default: throw BridgeError.invalid("Unknown transcription operation: \(request.operation)")
        }
        #endif
    }
}
