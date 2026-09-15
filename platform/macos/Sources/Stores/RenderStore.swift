import AppKit
import Foundation

@MainActor
final class RenderStore: ObservableObject {
    @Published var imageURL: URL?
    @Published var audioURL: URL?
    @Published var outputURL: URL?
    @Published var presets: [Preset] = []
    @Published var selectedPlatform = "Instagram"
    @Published var selectedAspect = "Horizontal video (16:9)"
    @Published var selectedPreset: Preset?
    @Published var flipHorizontal = false
    @Published var flipVertical = false
    @Published var bitrate = UserDefaults.standard.string(forKey: "audioBitrate") ?? "128k"
    @Published var fps = UserDefaults.standard.integer(forKey: "fps") == 0 ? 30 : UserDefaults.standard.integer(forKey: "fps")
    @Published var duration: Double?
    @Published var previewImage: NSImage?
    @Published var progress = 0.0
    @Published var status = "Loading media engine…"
    @Published var isRendering = false
    @Published var errorMessage: String?
    @Published var showDiagnostics = false
    @Published var diagnostics: [String] = []

    private let engine = EngineClient()
    private var previewGeneration = 0
    private var audioGeneration = 0
    private var terminating = false

    var platforms: [String] { unique(presets.map(\.platform)) }
    var aspects: [String] { unique(presets.filter { $0.platform == selectedPlatform }.map(\.aspect)) }
    var resolutions: [Preset] { presets.filter { $0.platform == selectedPlatform && $0.aspect == selectedAspect } }
    var canRender: Bool {
        imageURL != nil && audioURL != nil && outputURL != nil && selectedPreset != nil && !isRendering
        && outputURL != imageURL && outputURL != audioURL
    }

    func start() {
        guard presets.isEmpty else { return }
        engine.fetchPresets { [weak self] result in
            DispatchQueue.main.async {
                guard let self else { return }
                switch result {
                case .success(let presets):
                    self.presets = presets
                    self.normalizeSelection()
                    self.status = "Choose an image and audio recording."
                    if let path = ProcessInfo.processInfo.environment["ATIV_SMOKE_REPORT"], presets.count == 27 {
                        try? Data("{\"startup\":true,\"presets\":27}".utf8).write(to: URL(fileURLWithPath:path), options:.atomic)
                    }
                case .failure(let error): self.fail(error)
                }
            }
        }
    }

    func chooseImage() { guard !isRendering else { return }; if let url = PanelService.chooseImage() { setImage(url) } }
    func chooseAudio() { guard !isRendering else { return }; if let url = PanelService.chooseAudio() { setAudio(url) } }
    func chooseOutput() { guard !isRendering else { return }; if let url = PanelService.chooseOutput(suggested: suggestedOutput) { outputURL = url } }

    func setImage(_ url: URL) { guard !isRendering else { return }; imageURL = url; suggestOutputIfNeeded(); refreshPreview() }
    func setAudio(_ url: URL) {
        guard !isRendering else { return }
        audioGeneration += 1
        let generation = audioGeneration
        audioURL = url
        duration = nil
        status = "Reading audio duration…"
        suggestOutputIfNeeded()
        engine.probe(audio: url) { [weak self] result in
            DispatchQueue.main.async {
                guard let self else { return }
                guard generation == self.audioGeneration else { return }
                switch result {
                case .success(let value): self.duration = value; self.status = "Ready to create video."
                case .failure(let error): self.fail(error)
                }
            }
        }
    }

    func selectionChanged() { normalizeSelection(); refreshPreview() }
    func previewOptionsChanged() { refreshPreview() }

    func render() {
        guard !isRendering else { return }
        guard let imageURL, let audioURL, let outputURL, let preset = selectedPreset else {
            errorMessage = "Choose an image, audio recording, output destination, and format."
            return
        }
        guard outputURL != imageURL && outputURL != audioURL else {
            errorMessage = "The output destination must be separate from the image and audio source files."
            return
        }
        let validFps = max(1, min(240, fps))
        UserDefaults.standard.set(bitrate, forKey: "audioBitrate")
        UserDefaults.standard.set(validFps, forKey: "fps")
        progress = 0
        diagnostics = []
        isRendering = true
        status = "Preparing video…"
        let exportStarted = ProcessInfo.processInfo.systemUptime
        engine.render(image: imageURL, audio: audioURL, output: outputURL, preset: preset, bitrate: bitrate, fps: validFps, flipHorizontal: flipHorizontal, flipVertical: flipVertical) { [weak self] event in
            DispatchQueue.main.async { self?.apply(event) }
        } completion: { [weak self] result in
            DispatchQueue.main.async {
                guard let self else { return }
                self.isRendering = false
                let exportSeconds = ProcessInfo.processInfo.systemUptime - exportStarted
                self.diagnostics.append(String(format: "Export wall time: %.3f seconds", exportSeconds))
                if self.terminating { NSApp.reply(toApplicationShouldTerminate: true); return }
                switch result {
                case .success:
                    self.progress = 1
                    self.status = "Video saved as \(outputURL.lastPathComponent) in \(String(format: "%.1f", exportSeconds)) seconds."
                    NSDocumentController.shared.noteNewRecentDocumentURL(outputURL)
                case .failure(let error): self.fail(error)
                }
            }
        }
    }

    func requestTermination() -> NSApplication.TerminateReply {
        guard isRendering else { return .terminateNow }
        terminating = true
        cancel()
        return .terminateLater
    }

    func cancel() { status = "Stopping safely…"; engine.cancelRender() }

    func refreshPreview() {
        guard let imageURL, let preset = selectedPreset else { previewImage = nil; return }
        previewGeneration += 1
        let generation = previewGeneration
        let ratio = Double(preset.width) / Double(preset.height)
        let width = ratio >= 1 ? 360 : Int(360 * ratio)
        let height = ratio >= 1 ? Int(360 / ratio) : 360
        let evenWidth = max(2, width - width % 2)
        let evenHeight = max(2, height - height % 2)
        let output = FileManager.default.temporaryDirectory.appendingPathComponent("ativ-preview-\(UUID().uuidString).png")
        engine.preview(image: imageURL, output: output, width: evenWidth, height: evenHeight, flipHorizontal: flipHorizontal, flipVertical: flipVertical) { [weak self] result in
            DispatchQueue.main.async {
                if case .failure(let error) = result, generation == self?.previewGeneration { self?.fail(error) }
                if case .success(let url) = result {
                    let image = NSImage(contentsOf: url)
                    try? FileManager.default.removeItem(at: url)
                    guard let self, generation == self.previewGeneration else { return }
                    self.previewImage = image
                }
            }
        }
    }

    private var suggestedOutput: URL? {
        guard let source = audioURL ?? imageURL else { return nil }
        if source.pathExtension.lowercased() == "mp4" {
            let stem = source.deletingPathExtension().lastPathComponent
            return source.deletingLastPathComponent().appendingPathComponent("\(stem)-video.mp4")
        }
        return source.deletingPathExtension().appendingPathExtension("mp4")
    }
    private func suggestOutputIfNeeded() {
        if outputURL == nil || outputURL == audioURL || outputURL == imageURL {
            outputURL = suggestedOutput
        }
    }

    private func normalizeSelection() {
        if !platforms.contains(selectedPlatform) { selectedPlatform = platforms.first ?? "" }
        if !aspects.contains(selectedAspect) { selectedAspect = aspects.first ?? "" }
        if selectedPreset == nil || !resolutions.contains(selectedPreset!) { selectedPreset = resolutions.first }
    }

    private func apply(_ event: EngineEvent) {
        switch event.event {
        case "stage": status = stageText(event.stage)
        case "progress": progress = event.fraction ?? progress; status = progressText(event)
        case "error": errorMessage = event.message
        default: break
        }
        if diagnostics.count >= 500 { diagnostics.removeFirst(diagnostics.count - 499) }
        diagnostics.append(event.stage ?? event.event)
    }

    private func stageText(_ stage: String?) -> String {
        switch stage {
        case "validating": return "Checking files…"
        case "probing": return "Reading media…"
        case "compositing": return "Building frame…"
        case "encoding": return "Creating video…"
        case "publishing": return "Saving completed video…"
        case "complete": return "Complete"
        default: return "Working…"
        }
    }
    private func progressText(_ event: EngineEvent) -> String {
        let percent = Int((event.fraction ?? 0) * 100)
        if let eta = event.etaSeconds { return "Creating video — \(percent)% — about \(format(eta)) remaining" }
        return "Creating video — \(percent)%"
    }
    private func format(_ seconds: Double) -> String {
        let total = max(0, Int(seconds.rounded()))
        if total >= 3600 {
            return String(format: "%d:%02d:%02d", total / 3600, (total % 3600) / 60, total % 60)
        }
        return String(format: "%d:%02d", total / 60, total % 60)
    }
    private func fail(_ error: Error) { errorMessage = error.localizedDescription; status = "Unable to complete the operation." }
    private func unique(_ values: [String]) -> [String] { values.reduce(into: []) { if !$0.contains($1) { $0.append($1) } } }
}
