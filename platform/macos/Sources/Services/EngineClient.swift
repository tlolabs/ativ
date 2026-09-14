import Foundation

enum EngineClientError: LocalizedError {
    case missingEngine
    case launchFailed(String)
    case operationFailed(String)

    var errorDescription: String? {
        switch self {
        case .missingEngine: return "The ATIV media engine is missing. Reinstall the application."
        case .launchFailed(let detail), .operationFailed(let detail): return detail
        }
    }
}

final class EngineClient {
    private let lock = NSLock()
    private var renderProcess: Process?

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
        runCapture(arguments: ["probe", "--audio", audio.path]) { result in
            completion(result.map { $0.first(where: { $0.event == "probe" })?.durationSeconds })
        }
    }

    func preview(image: URL, output: URL, width: Int, height: Int, flipHorizontal: Bool, flipVertical: Bool, completion: @escaping (Result<URL, Error>) -> Void) {
        var arguments = ["preview", "--image", image.path, "--output", output.path, "--width", String(width), "--height", String(height)]
        if flipHorizontal { arguments.append("--flip-horizontal") }
        if flipVertical { arguments.append("--flip-vertical") }
        runCapture(arguments: arguments) { result in completion(result.map { _ in output }) }
    }

    func render(image: URL, audio: URL, output: URL, preset: Preset, bitrate: String, fps: Int, flipHorizontal: Bool, flipVertical: Bool, event: @escaping (EngineEvent) -> Void, completion: @escaping (Result<Void, Error>) -> Void) {
        guard let engineURL else { completion(.failure(EngineClientError.missingEngine)); return }
        var arguments = ["render", "--image", image.path, "--audio", audio.path, "--output", output.path, "--width", String(preset.width), "--height", String(preset.height), "--audio-bitrate", bitrate, "--fps", String(fps)]
        if flipHorizontal { arguments.append("--flip-horizontal") }
        if flipVertical { arguments.append("--flip-vertical") }

        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process(), stdout = Pipe(), stdin = Pipe()
            process.executableURL = engineURL
            process.arguments = arguments
            process.standardOutput = stdout
            process.standardError = FileHandle.nullDevice
            process.standardInput = stdin
            self.lock.lock(); self.renderProcess = process; self.lock.unlock()
            do { try process.run() } catch {
                self.clear(process)
                completion(.failure(EngineClientError.launchFailed("Could not start the media engine: \(error.localizedDescription)")))
                return
            }
            var lastError: String?
            self.consumeLines(from: stdout.fileHandleForReading) { item in
                if item.event == "error" { lastError = item.message }
                event(item)
            }
            process.waitUntilExit()

            self.clear(process)
            if process.terminationStatus == 0 { completion(.success(())); return }
            if process.terminationStatus == 130 { completion(.failure(EngineClientError.operationFailed("Video creation was stopped. The previous output was preserved."))); return }
            let detail = lastError ?? "The media engine could not finish this operation."
            completion(.failure(EngineClientError.operationFailed(detail)))
        }
    }

    func cancelRender() {
        lock.lock(); let process = renderProcess; lock.unlock()
        guard let handle = (process?.standardInput as? Pipe)?.fileHandleForWriting else { return }
        try? handle.write(contentsOf: Data("cancel\n".utf8))
    }

    private func runCapture(arguments: [String], completion: @escaping (Result<[EngineEvent], Error>) -> Void) {
        guard let engineURL else { completion(.failure(EngineClientError.missingEngine)); return }
        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process(), output = Pipe()
            process.executableURL = engineURL
            process.arguments = arguments
            process.standardOutput = output
            process.standardError = FileHandle.nullDevice
            process.standardInput = FileHandle.nullDevice
            do { try process.run() } catch {
                completion(.failure(EngineClientError.launchFailed("Could not start the media engine: \(error.localizedDescription)"))); return
            }
            let data = output.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            let events = String(data: data, encoding: .utf8)?.split(separator: "\n").compactMap { try? JSONDecoder().decode(EngineEvent.self, from: Data($0.utf8)) } ?? []
            if process.terminationStatus == 0 { completion(.success(events)); return }
            let message = events.last(where: { $0.event == "error" })?.message ?? "The media engine could not complete this operation."
            completion(.failure(EngineClientError.operationFailed(message)))
        }
    }

    private func consumeLines(from handle: FileHandle, event: (EngineEvent) -> Void) {
        var buffer = Data()
        while true {
            let data = handle.availableData
            if data.isEmpty { break }
            buffer.append(data)
            while let newline = buffer.firstIndex(of: 10) {
                let line = buffer[..<newline]
                buffer.removeSubrange(...newline)
                if let decoded = try? JSONDecoder().decode(EngineEvent.self, from: line) { event(decoded) }
            }
        }
    }

    private func clear(_ process: Process) {
        lock.lock(); if renderProcess === process { renderProcess = nil }; lock.unlock()
    }
}
