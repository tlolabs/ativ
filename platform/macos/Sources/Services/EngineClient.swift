// SPDX-License-Identifier: GPL-3.0-or-later
import Foundation

enum EngineClientError: LocalizedError, Equatable {
    case missingEngine
    case launchFailed
    case operationFailed(String)
    case cancelled

    var errorDescription: String? {
        switch self {
        case .missingEngine: return "The ATIV media engine is missing. Reinstall the application."
        case .launchFailed: return "The ATIV media engine could not start. Reinstall the complete application and try again."
        case .operationFailed(let detail): return detail
        case .cancelled: return "Video creation was stopped. The previous output was preserved."
        }
    }
}

final class EngineClient {
    // Serial across clients: a superseded process must exit before another Core
    // operation starts. This also bounds the four artwork probes in each render
    // and serializes writers to the same destination within the application.
    private static let worker = DispatchQueue(label: "com.tlolabs.ativ.engine", qos: .userInitiated)
    private let lock = NSLock()
    private var pendingOperations = 0

    var hasPendingWork: Bool {
        lock.lock()
        defer { lock.unlock() }
        return pendingOperations != 0
    }

    func whenIdle(completion: @escaping () -> Void) {
        Self.worker.async(execute: completion)
    }

    private func enqueue(_ operation: @escaping () -> Void) {
        lock.lock()
        pendingOperations += 1
        lock.unlock()
        Self.worker.async {
            defer {
                self.lock.lock()
                self.pendingOperations -= 1
                self.lock.unlock()
            }
            operation()
        }
    }
    private var currentRenderId: UUID?
    private var cancelledRenderIds: Set<UUID> = []
    private var renderProcess: Process?

    private var currentPreviewId: UUID?
    private var cancelledPreviewIds: Set<UUID> = []
    private var previewProcess: Process?

    private var currentProbeId: UUID?
    private var cancelledProbeIds: Set<UUID> = []
    private var probeProcess: Process?

    private var engineURL: URL? {
        if let configured = ProcessInfo.processInfo.environment["ATIV_ENGINE_PATH"] { return URL(fileURLWithPath: configured) }
        let bundled = Bundle.main.bundleURL.appendingPathComponent("Contents/MacOS/ativ-engine")
        if FileManager.default.isExecutableFile(atPath: bundled.path) { return bundled }
        let local = URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("target/debug/ativ-engine")
        return FileManager.default.isExecutableFile(atPath: local.path) ? local : nil
    }

    func fetchPresets(completion: @escaping (Result<[Preset], Error>) -> Void) {
        runCapture(arguments: ["presets"]) { result in
            completion(result.flatMap { events in
                if let items = events.first(where: { $0.event == "presets" })?.items { return .success(items) }
                return .failure(EngineClientError.operationFailed("The media engine returned no format presets."))
            })
        }
    }

    func probe(audio: URL, completion: @escaping (Result<Double?, Error>) -> Void) {
        cancelProbe()
        let requestId = UUID()
        lock.lock()
        currentProbeId = requestId
        lock.unlock()

        runCapture(arguments: ["probe", "--audio", audio.path], requestId: requestId, isCancelled: { [weak self] id in
            guard let self else { return true }
            self.lock.lock()
            defer { self.lock.unlock() }
            return self.cancelledProbeIds.contains(id) || self.currentProbeId != id
        }, assign: { [weak self] p in
            self?.lock.lock(); self?.probeProcess = p; self?.lock.unlock()
        }, clear: { [weak self] p in
            self?.lock.lock()
            if self?.probeProcess === p { self?.probeProcess = nil }
            self?.cancelledProbeIds.remove(requestId)
            self?.lock.unlock()
        }) { result in
            completion(result.map { $0.first(where: { $0.event == "probe" })?.durationSeconds })
        }
    }

    func cancelProbe() {
        lock.lock()
        if let id = currentProbeId { cancelledProbeIds.insert(id) }
        let process = probeProcess
        probeProcess = nil
        lock.unlock()
        if let process {
            terminateProcessGracefully(process)
        }
    }

    func preview(image: URL, output: URL, width: Int, height: Int, flipHorizontal: Bool, flipVertical: Bool, protectedPaths: [URL] = [], completion: @escaping (Result<URL, Error>) -> Void) {
        cancelPreview()
        var arguments = ["preview", "--image", image.path, "--output", output.path, "--width", String(width), "--height", String(height)]
        for protected in protectedPaths { arguments += ["--protected-path", protected.path] }
        if flipHorizontal { arguments.append("--flip-horizontal") }
        if flipVertical { arguments.append("--flip-vertical") }

        let requestId = UUID()
        lock.lock()
        currentPreviewId = requestId
        lock.unlock()

        runCapture(arguments: arguments, requestId: requestId, isCancelled: { [weak self] id in
            guard let self else { return true }
            self.lock.lock()
            defer { self.lock.unlock() }
            return self.cancelledPreviewIds.contains(id) || self.currentPreviewId != id
        }, assign: { [weak self] p in
            self?.lock.lock(); self?.previewProcess = p; self?.lock.unlock()
        }, clear: { [weak self] p in
            self?.lock.lock()
            if self?.previewProcess === p { self?.previewProcess = nil }
            self?.cancelledPreviewIds.remove(requestId)
            self?.lock.unlock()
        }) { result in
            switch result {
            case .success:
                completion(.success(output))
            case .failure(let error):
                // Core owns staged output cleanup and preserves prior destinations.
                completion(.failure(error))
            }
        }
    }

    func cancelPreview() {
        lock.lock()
        if let id = currentPreviewId { cancelledPreviewIds.insert(id) }
        let process = previewProcess
        previewProcess = nil
        lock.unlock()
        if let process {
            terminateProcessGracefully(process)
        }
    }

    func render(image: URL, audio: URL, output: URL, preset: Preset, bitrate: String, fps: Int, flipHorizontal: Bool, flipVertical: Bool, event: @escaping (EngineEvent) -> Void, completion: @escaping (Result<Void, Error>) -> Void) {
        guard let engineURL else { completion(.failure(EngineClientError.missingEngine)); return }
        cancelRender()
        cancelPreview()
        cancelProbe()
        var arguments = ["render", "--image", image.path, "--audio", audio.path, "--output", output.path, "--width", String(preset.width), "--height", String(preset.height), "--audio-bitrate", bitrate, "--fps", String(fps)]
        if flipHorizontal { arguments.append("--flip-horizontal") }
        if flipVertical { arguments.append("--flip-vertical") }

        let requestId = UUID()
        lock.lock()
        currentRenderId = requestId
        lock.unlock()

        enqueue {
            self.lock.lock()
            if self.cancelledRenderIds.contains(requestId) || self.currentRenderId != requestId {
                self.cancelledRenderIds.remove(requestId)
                self.lock.unlock()
                completion(.failure(EngineClientError.cancelled))
                return
            }
            let process = Process(), stdout = Pipe(), stdin = Pipe()
            process.executableURL = engineURL
            process.arguments = arguments
            process.standardOutput = stdout
            process.standardError = FileHandle.nullDevice
            process.standardInput = stdin
            self.renderProcess = process
            self.lock.unlock()

            do {
                try process.run()
            } catch {
                NSLog("ATIV media engine launch failed: %@", error.localizedDescription)
                self.lock.lock()
                if self.renderProcess === process { self.renderProcess = nil }
                self.cancelledRenderIds.remove(requestId)
                self.lock.unlock()
                completion(.failure(EngineClientError.launchFailed))
                return
            }

            self.lock.lock()
            let wasCancelledBeforeRun = self.cancelledRenderIds.contains(requestId) || self.currentRenderId != requestId
            self.lock.unlock()
            if wasCancelledBeforeRun {
                self.terminateProcessGracefully(process)
            }

            var lastError: String?
            var published = false
            self.consumeLines(from: stdout.fileHandleForReading) { item in
                if item.event == "error" { lastError = item.message }
                if item.stage == "complete" { published = true }
                event(item)
            }
            process.waitUntilExit()

            self.lock.lock()
            if self.renderProcess === process { self.renderProcess = nil }
            let isCancelled = self.cancelledRenderIds.contains(requestId) || self.currentRenderId != requestId
            self.cancelledRenderIds.remove(requestId)
            self.lock.unlock()

            // A late Stop cannot turn an already published output into a failure.
            if published || process.terminationStatus == 0 {
                completion(.success(()))
                return
            }
            if isCancelled || process.terminationStatus == 130 {
                completion(.failure(EngineClientError.cancelled))
                return
            }
            let detail = lastError ?? "The media engine could not finish this operation."
            completion(.failure(EngineClientError.operationFailed(detail)))
        }
    }

    func cancelRender() {
        lock.lock()
        if let id = currentRenderId {
            cancelledRenderIds.insert(id)
        }
        let process = renderProcess
        lock.unlock()

        if let process {
            terminateProcessGracefully(process)
        }
    }

    private func terminateProcessGracefully(_ process: Process) {
        guard process.isRunning else { return }
        if let handle = (process.standardInput as? Pipe)?.fileHandleForWriting {
            try? handle.write(contentsOf: Data("cancel\n".utf8))
        }
        DispatchQueue.global(qos: .utility).async {
            let start = ProcessInfo.processInfo.systemUptime
            while process.isRunning && (ProcessInfo.processInfo.systemUptime - start) < 1.5 {
                usleep(50000)
            }
            if process.isRunning {
                process.terminate()
                let termStart = ProcessInfo.processInfo.systemUptime
                while process.isRunning && (ProcessInfo.processInfo.systemUptime - termStart) < 0.5 {
                    usleep(50000)
                }
                if process.isRunning {
                    let pid = process.processIdentifier
                    if pid > 0 {
                        kill(-pid, SIGKILL)
                        kill(pid, SIGKILL)
                    }
                }
            }
        }
    }

    private func runCapture(arguments: [String],
                            requestId: UUID? = nil,
                            isCancelled: ((UUID) -> Bool)? = nil,
                            assign: ((Process) -> Void)? = nil,
                            clear: ((Process?) -> Void)? = nil,
                            completion: @escaping (Result<[EngineEvent], Error>) -> Void) {
        guard let engineURL else { completion(.failure(EngineClientError.missingEngine)); return }
        enqueue {
            if let requestId, let isCancelled, isCancelled(requestId) {
                if let clear { clear(nil) }
                completion(.failure(EngineClientError.cancelled))
                return
            }
            let process = Process(), output = Pipe(), stdin = Pipe()
            process.executableURL = engineURL
            process.arguments = arguments
            process.standardOutput = output
            process.standardError = FileHandle.nullDevice
            process.standardInput = stdin
            if let assign { assign(process) }

            if let requestId, let isCancelled, isCancelled(requestId) {
                if let clear { clear(process) }
                completion(.failure(EngineClientError.cancelled))
                return
            }

            do {
                try process.run()
            } catch {
                NSLog("ATIV media engine launch failed: %@", error.localizedDescription)
                if let clear { clear(process) }
                completion(.failure(EngineClientError.launchFailed))
                return
            }

            if let requestId, let isCancelled, isCancelled(requestId) {
                self.terminateProcessGracefully(process)
            }

            var events: [EngineEvent] = []
            self.consumeLines(from: output.fileHandleForReading) { events.append($0) }
            process.waitUntilExit()
            let cancelledAfterExit = (requestId != nil && isCancelled != nil) ? isCancelled!(requestId!) : false
            if let clear { clear(process) }

            let published = events.contains { $0.stage == "complete" || $0.event == "complete" }
            if published || process.terminationStatus == 0 { completion(.success(events)); return }
            if cancelledAfterExit || process.terminationStatus == 130 {
                completion(.failure(EngineClientError.cancelled))
                return
            }
            let message = events.last(where: { $0.event == "error" })?.message ?? "The media engine could not complete this operation."
            completion(.failure(EngineClientError.operationFailed(message)))
        }
    }

    private func consumeLines(from handle: FileHandle, event: (EngineEvent) -> Void) {
        var stream = EngineEventStream()
        while true {
            let data = handle.availableData
            if data.isEmpty { break }
            stream.consume(data, event: event)
        }
        stream.consume(Data(), endOfFile: true, event: event)
    }
}

// Operation-local byte framing preserves fragmented UTF-8 and the existing
// policy of ignoring malformed/empty lines, including an incomplete EOF record.
struct EngineEventStream {
    static let maximumLineBytes = 8 * 1024 * 1024
    private(set) var pending = Data()
    private var discarding = false
    private let decoder = JSONDecoder()

    mutating func consume(_ data: Data, endOfFile: Bool = false, event: (EngineEvent) -> Void) {
        var start = data.startIndex
        while start < data.endIndex {
            let newline = data[start...].firstIndex(of: 10)
            let end = newline ?? data.endIndex
            let bytes = data[start..<end]
            if !discarding {
                if bytes.count > Self.maximumLineBytes - pending.count {
                    pending.removeAll(keepingCapacity: false)
                    discarding = true
                } else if pending.isEmpty, newline != nil {
                    if let value = try? decoder.decode(EngineEvent.self, from: bytes) { event(value) }
                } else {
                    pending.append(bytes)
                    if newline != nil {
                        if let value = try? decoder.decode(EngineEvent.self, from: pending) { event(value) }
                        pending.removeAll(keepingCapacity: true)
                    }
                }
            }
            if let newline {
                discarding = false
                start = data.index(after: newline)
            } else { break }
        }
        if endOfFile {
            if !discarding, let value = try? decoder.decode(EngineEvent.self, from: pending) { event(value) }
            pending.removeAll(keepingCapacity: false)
            discarding = false
        }
    }
}
