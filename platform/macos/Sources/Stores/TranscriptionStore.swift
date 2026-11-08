import AppKit
import Foundation
import UniformTypeIdentifiers

/// The app keeps Core's canonical transcript JSON intact; only the isolated helper edits it.
@MainActor
final class TranscriptionStore: ObservableObject {
    typealias Runner = @Sendable (JSONValue, @escaping @Sendable (JSONValue) -> Void) async throws -> JSONValue

    struct Model: Identifiable, Equatable {
        let value: JSONValue
        var id: String { value["id"]?.stringValue ?? "" }
        var name: String { value["displayName"]?.stringValue ?? id }
        var role: String { value["role"]?.stringValue ?? "" }
        var installed: Bool { value["installed"]?.boolValue ?? false }
        var bytes: Double { value["downloadBytes"]?.doubleValue ?? 0 }
        var diskBytes: Double { value["diskBytes"]?.doubleValue ?? 0 }
        var partialBytes: Double { value["partialBytes"]?.doubleValue ?? 0 }
        var timingLanguages: [String] { value["timingLanguages"]?.arrayValue?.compactMap(\.stringValue) ?? [] }
        var notice: String { value["license"]?["notice"]?.stringValue ?? "" }
    }

    @Published private(set) var models: [Model] = []
    @Published var selectedModelID = "whisper-large-v3"
    @Published var managedModelID = "whisper-large-v3"
    @Published var alignmentModelID = "qwen3-forced-aligner-0.6b-4bit"
    @Published var language = ""
    @Published private(set) var sourceURL: URL?
    @Published private(set) var document: TranscriptionDocument?
    @Published private(set) var sourceMatchesDocument = false
    @Published private(set) var isBusy = false { didSet { workStateChanged?() } }
    @Published private(set) var status = "Local transcription"
    @Published private(set) var progress: Double?
    @Published var errorMessage: String?
    @Published var selectedSegment = 0
    @Published private(set) var segmentDrafts: [Int: String] = [:]
    @Published private(set) var hasUnsavedChanges = false
    @Published private(set) var cues: [JSONValue] = []
    @Published var previewTime = 0.0
    @Published var maximumWords = 6
    @Published var maximumCharacters = 42
    @Published var maximumDuration = 3.0
    @Published var maximumPause = 0.6
    @Published var trimStart = 0.0
    @Published var trimEnd = ""
    @Published var timelineStart = 0.0
    @Published private(set) var captionsNeedRefresh = true
    @Published private(set) var cachePath = ""

    var protectedMediaURLs: [URL] = []
    var workStateChanged: (() -> Void)?
    let capability: TranscriptionCapability
    private let client: TranscriptionClient
    private let runner: Runner
    private var operationTask: Task<Void, Never>?
    private var sourceTask: Task<Void, Never>?
    private var sourceGeneration = UUID()
    private var operationID = UUID()
    private var operationSourceGeneration: UUID?
    private var closed = false
    private var cancelling = false
    private var committedUnsavedChanges = false
    private var savedCaptionPreferences: JSONValue?
    private var lastCaptionPreferences: JSONValue?
    private var subtitleSRT = ""
    private var subtitleVTT = ""

    init(client: TranscriptionClient = TranscriptionClient(), runner: Runner? = nil,
         capability: TranscriptionCapability? = nil) {
        self.client = client
        self.runner = runner ?? { request, progress in try await client.run(request: request, progress: progress) }
        self.capability = capability ?? client.capability
    }

    var recognitionModels: [Model] { models.filter { $0.role == "recognizer" } }
    var alignmentModels: [Model] { models.filter { $0.role == "aligner" } }
    var selectedModel: Model? { models.first { $0.id == selectedModelID } }
    var managedModel: Model? { models.first { $0.id == managedModelID } }
    var segments: [JSONValue] { document?.transcript["segments"]?.arrayValue ?? [] }
    var selectedSegmentText: String {
        guard segments.indices.contains(selectedSegment) else { return "" }
        return segmentDrafts[selectedSegment] ?? segments[selectedSegment]["text"]?.stringValue ?? ""
    }
    var hasPendingTextEdits: Bool { !segmentDrafts.isEmpty }
    var hasTranscript: Bool { document != nil }
    var hasWordTiming: Bool {
        guard document != nil, !hasPendingTextEdits else { return false }
        return segments.allSatisfy { segment in
            let text = segment["text"]?.stringValue ?? ""
            if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return true }
            let words = segment["words"]?.arrayValue ?? []
            return !words.isEmpty && words.allSatisfy {
                $0["startSeconds"]?.doubleValue != nil && $0["endSeconds"]?.doubleValue != nil
            }
        }
    }
    var canTranscribe: Bool { capability.isSupported && sourceURL != nil && !isBusy && selectedModel?.installed == true }
    var canAlign: Bool {
        capability.isSupported && sourceURL != nil && document != nil && sourceMatchesDocument && !isBusy
            && models.first(where: { $0.id == alignmentModelID })?.installed == true
    }
    var previewDuration: Double { max(1, cues.compactMap { $0["endSeconds"]?.doubleValue }.max() ?? 1) }
    var activeCue: JSONValue? {
        cues.first { cue in
            guard let start = cue["startSeconds"]?.doubleValue, let end = cue["endSeconds"]?.doubleValue else { return false }
            return previewTime >= start && previewTime < end
        }
    }

    func setSource(_ url: URL?) {
        guard sourceURL != url || closed else { return }
        closed = false
        sourceGeneration = UUID()
        sourceTask?.cancel()
        // Catalog and model-cache operations do not consume the selected recording.
        // Keep their progress/results valid while independently changing audio.
        if isBusy, operationSourceGeneration != nil {
            operationTask?.cancel()
            client.cancelAll()
            cancelling = true
            status = "Audio source changed; stopping the previous operation safely…"
        }
        sourceURL = url
        sourceMatchesDocument = false
        let generation = sourceGeneration
        guard let url, let document else { return }
        sourceTask = Task { [weak self] in
            do {
                let matches = try await document.source.matches(url)
                guard let self, self.sourceGeneration == generation, !Task.isCancelled else { return }
                self.sourceMatchesDocument = matches
                if !matches && !self.isBusy { self.status = "Transcript retained for another audio source. Reopen its matching recording to realign." }
            } catch {
                guard let self, self.sourceGeneration == generation, !Task.isCancelled else { return }
                self.errorMessage = error.localizedDescription
            }
        }
    }

    func close() {
        closed = true
        sourceGeneration = UUID()
        sourceTask?.cancel()
        operationTask?.cancel()
        client.cancelAll()
        cancelling = isBusy
    }

    func cancel() {
        guard isBusy else { return }
        status = "Stopping safely; a model kernel may finish before cancellation…"
        operationTask?.cancel()
        client.cancelAll()
        cancelling = true
    }

    func cancelAndWait() async {
        cancel()
        await operationTask?.value
        sourceTask?.cancel()
        await sourceTask?.value
        await withCheckedContinuation { continuation in client.whenIdle { continuation.resume() } }
    }

    func waitForCurrentOperation() async { await operationTask?.value }
    func waitForSourceIdentity() async { await sourceTask?.value }

    func confirmTerminationWithUnsavedChanges() -> Bool {
        guard hasUnsavedChanges else { return true }
        let alert = NSAlert()
        alert.messageText = "Quit with unsaved transcript changes?"
        alert.informativeText = "Choose Keep Editing, then save the transcript to preserve your corrections and caption settings."
        alert.addButton(withTitle: "Keep Editing")
        alert.addButton(withTitle: "Discard and Quit")
        return alert.runModal() == .alertSecondButtonReturn
    }

    func loadCatalog() {
        guard capability.isSupported, models.isEmpty, !isBusy else { return }
        refreshCatalog()
    }

    func refreshCatalog() {
        guard capability.isSupported, !isBusy else { return }
        begin("Reading model catalog…", sourceDependent: false) { id in
            try await self.refreshModels(id: id)
            self.status = "Model catalog ready. Install or import a model to begin."
        }
    }

    func modelOperation(_ operation: String, localURL: URL? = nil) {
        guard capability.isSupported, !isBusy else { return }
        let modelID = managedModelID
        begin("\(operation.capitalized) model…", sourceDependent: false) { id in
            var request: [String: JSONValue] = ["operation": .string(operation), "modelID": .string(modelID)]
            if let localURL { request["localPath"] = .string(localURL.path) }
            _ = try await self.run(request, id: id)
            try await self.refreshModels(id: id)
            self.status = "Model \(operation) complete."
        }
    }

    func chooseModelFolder() {
        let panel = NSOpenPanel()
        panel.title = "Import a catalog-compatible model folder"
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url { modelOperation("import", localURL: url) }
    }

    func transcribe() {
        guard canTranscribe, let audioURL = sourceURL else { return }
        if hasTranscript && !confirmReplacement() { return }
        let modelID = selectedModelID
        let hint = language.trimmingCharacters(in: .whitespacesAndNewlines)
        begin("Recognizing locally…") { id in
            let identity = try await TranscriptionSourceIdentity.fingerprint(of: audioURL)
            try self.check(id)
            var request: [String: JSONValue] = ["operation": .string("transcribe"), "audioPath": .string(audioURL.path), "modelID": .string(modelID)]
            if !hint.isEmpty { request["language"] = .string(hint) }
            let result = try await self.run(request, id: id)
            guard let transcript = result["transcript"] else { throw StoreError.invalidResult }
            guard try await identity.matches(audioURL) else { throw StoreError.changedSource }
            try self.check(id)
            self.document = TranscriptionDocument(source: identity, transcript: transcript, captionPreferences: self.preferences)
            self.sourceMatchesDocument = true
            self.segmentDrafts = [:]
            self.selectedSegment = 0
            self.committedUnsavedChanges = true
            self.savedCaptionPreferences = self.preferences
            self.lastCaptionPreferences = self.preferences
            self.updateUnsavedState()
            self.invalidateCaptions()
            self.status = self.hasWordTiming ? "Transcript ready. Review the text before exporting captions." : "Text recognized without word timing. Install the aligner and realign to create captions."
        }
    }

    func updateSelectedText(_ text: String) {
        guard segments.indices.contains(selectedSegment), !isBusy else { return }
        guard text != selectedSegmentText else { return }
        if text == segments[selectedSegment]["text"]?.stringValue { segmentDrafts.removeValue(forKey: selectedSegment) }
        else { segmentDrafts[selectedSegment] = text }
        updateUnsavedState()
        invalidateCaptions()
    }

    func applyEdits() {
        guard hasPendingTextEdits, !isBusy else { return }
        begin("Applying text corrections…") { id in
            try await self.commitEdits(id: id)
            self.status = "Text corrected. Affected word timings were removed; realign to restore them."
        }
    }

    func align() {
        guard canAlign, let audioURL = sourceURL else { return }
        let modelID = alignmentModelID
        let hint = language.trimmingCharacters(in: .whitespacesAndNewlines)
        begin("Aligning edited text locally…") { id in
            guard let source = self.document?.source, try await source.matches(audioURL) else { throw StoreError.changedSource }
            try self.check(id)
            try await self.commitEdits(id: id)
            guard let transcript = self.document?.transcript else { throw StoreError.invalidResult }
            var request: [String: JSONValue] = ["operation": .string("align"), "audioPath": .string(audioURL.path), "modelID": .string(modelID), "transcript": transcript]
            if !hint.isEmpty { request["language"] = .string(hint) }
            let result = try await self.run(request, id: id)
            guard try await source.matches(audioURL) else { throw StoreError.changedSource }
            try self.check(id)
            try self.replaceTranscript(result["transcript"])
            self.status = "Alignment complete. Recognition and alignment provenance are retained separately."
        }
    }

    func captionSettingsChanged() {
        guard document != nil else { return }
        updateUnsavedState()
        guard preferences != lastCaptionPreferences else { return }
        lastCaptionPreferences = preferences
        invalidateCaptions()
    }

    func generateCaptions() {
        guard hasWordTiming, !isBusy else { return }
        begin("Grouping timed captions…") { id in
            try await self.buildCaptions(id: id)
            self.status = "Caption preview and SRT/WebVTT ready."
        }
    }

    func saveDocument() {
        guard document != nil, !isBusy, let audioURL = sourceURL, sourceMatchesDocument else {
            errorMessage = "Choose the recording matching this transcript before saving."
            return
        }
        let panel = NSSavePanel()
        panel.title = "Save transcript and caption settings"
        panel.allowedContentTypes = [.json]
        panel.nameFieldStringValue = audioURL.deletingPathExtension().lastPathComponent + ".ativ-transcript.json"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let protectedURLs = protectedMediaURLs
        begin("Saving transcript…") { id in
            try self.protectDestination(url)
            try await self.commitEdits(id: id)
            guard let document = self.document, try await document.source.matches(audioURL) else { throw StoreError.changedSource }
            try self.check(id)
            let saved = TranscriptionDocument(source: document.source, transcript: document.transcript, captionPreferences: self.preferences)
            try await saved.save(to: url, sourceURL: audioURL, replacingExisting: true, protectedURLs: protectedURLs)
            try self.check(id)
            self.document = saved
            self.committedUnsavedChanges = false
            self.savedCaptionPreferences = saved.captionPreferences
            self.lastCaptionPreferences = self.preferences
            self.updateUnsavedState()
            self.status = "Saved \(url.lastPathComponent)."
        }
    }

    func openDocument() {
        guard !isBusy else { return }
        if hasUnsavedChanges && !confirmReplacement() { return }
        let panel = NSOpenPanel()
        panel.title = "Open ATIV transcript"
        panel.allowedContentTypes = [.json]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        loadDocument(from: url)
    }

    /// Reopen an explicitly selected document without discarding its canonical JSON fields.
    func loadDocument(from url: URL) {
        guard !isBusy else { return }
        begin("Opening transcript…") { id in
            let document = try await TranscriptionDocument.read(from: url)
            try self.check(id)
            // Core validates all timestamps and provenance before anything becomes editable.
            _ = try await self.run(["operation": .string("validate"), "transcript": document.transcript], id: id)
            let matches: Bool
            if let audioURL = self.sourceURL { matches = try await document.source.matches(audioURL) }
            else { matches = false }
            try self.check(id)
            self.document = document
            self.sourceMatchesDocument = matches
            self.segmentDrafts = [:]
            self.selectedSegment = 0
            self.restorePreferences(document.captionPreferences)
            self.committedUnsavedChanges = false
            self.savedCaptionPreferences = self.preferences
            self.lastCaptionPreferences = self.preferences
            self.updateUnsavedState()
            self.invalidateCaptions()
            self.status = matches ? "Transcript opened; source identity verified." : "Transcript opened. Select its matching recording to realign or save."
        }
    }

    func exportSubtitles(webVTT: Bool) {
        guard hasWordTiming, !isBusy, let audioURL = sourceURL, sourceMatchesDocument else { return }
        let panel = NSSavePanel()
        panel.title = webVTT ? "Export WebVTT captions" : "Export SRT captions"
        panel.allowedContentTypes = [UTType(filenameExtension: webVTT ? "vtt" : "srt") ?? .plainText]
        panel.nameFieldStringValue = audioURL.deletingPathExtension().lastPathComponent + (webVTT ? ".vtt" : ".srt")
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let protectedURLs = protectedMediaURLs
        begin("Exporting subtitle sidecar…") { id in
            try self.protectDestination(url)
            try await self.buildCaptions(id: id)
            let text = webVTT ? self.subtitleVTT : self.subtitleSRT
            try await TranscriptionDocument.write(data: Data(text.utf8), to: url, sourceURL: audioURL, replacingExisting: true, protectedURLs: protectedURLs)
            try self.check(id)
            self.status = "Saved \(url.lastPathComponent). Video exports contain no burned-in captions."
        }
    }

    private var preferences: JSONValue {
        .object(["maximumWords": .number(Double(maximumWords)), "maximumCharacters": .number(Double(maximumCharacters)),
                 "maximumDurationSeconds": .number(maximumDuration), "maximumPauseSeconds": .number(maximumPause),
                 "sourceStartSeconds": .number(trimStart), "sourceEndSeconds": Double(trimEnd).map(JSONValue.number) ?? .null,
                 "timelineStartSeconds": .number(timelineStart)])
    }

    private func restorePreferences(_ value: JSONValue) {
        maximumWords = Int(min(30, max(1, value["maximumWords"]?.doubleValue ?? 6)))
        maximumCharacters = Int(min(200, max(1, value["maximumCharacters"]?.doubleValue ?? 42)))
        maximumDuration = value["maximumDurationSeconds"]?.doubleValue ?? 3
        maximumPause = value["maximumPauseSeconds"]?.doubleValue ?? 0.6
        trimStart = value["sourceStartSeconds"]?.doubleValue ?? 0
        trimEnd = value["sourceEndSeconds"]?.doubleValue.map { String($0) } ?? ""
        timelineStart = value["timelineStartSeconds"]?.doubleValue ?? 0
    }

    private func begin(_ title: String, sourceDependent: Bool = true, action: @escaping @MainActor (UUID) async throws -> Void) {
        guard !isBusy, capability.isSupported, !closed else { return }
        let id = UUID()
        operationID = id
        let generation = sourceDependent ? sourceGeneration : nil
        operationSourceGeneration = generation
        isBusy = true
        cancelling = false
        progress = nil
        errorMessage = nil
        status = title
        operationTask = Task { [weak self] in
            guard let self else { return }
            do { try await action(id) }
            catch {
                if self.operationID == id, !self.closed {
                    let sourceChanged = generation.map { $0 != self.sourceGeneration } ?? false
                    let cancelled = Task.isCancelled || error is CancellationError || sourceChanged
                    self.status = sourceChanged ? "Audio source changed. Previous operation stopped safely." : cancelled ? "Operation stopped safely." : "Transcription operation failed."
                    if !cancelled { self.errorMessage = error.localizedDescription }
                }
            }
            // The runner only returns after the helper has exited and released its model leases.
            if self.operationID == id { self.isBusy = false; self.progress = nil; self.operationSourceGeneration = nil }
        }
    }

    private func run(_ request: [String: JSONValue], id: UUID) async throws -> JSONValue {
        try check(id)
        let generation = operationSourceGeneration
        let result = try await runner(.object(request)) { [weak self] event in
            Task { @MainActor in
                guard let self, self.operationID == id, self.isBusy,
                      generation.map({ self.sourceGeneration == $0 }) ?? true,
                      !self.closed, !self.cancelling else { return }
                if let message = event["message"]?.stringValue { self.status = message }
                self.progress = event["fraction"]?.doubleValue.map { max(0, min(1, $0)) }
            }
        }
        try check(id)
        return result
    }

    private func check(_ id: UUID) throws {
        try Task.checkCancellation()
        guard id == operationID, !closed else { throw CancellationError() }
        if let generation = operationSourceGeneration, generation != sourceGeneration { throw CancellationError() }
    }

    private func refreshModels(id: UUID) async throws {
        let result = try await run(["operation": .string("catalog")], id: id)
        models = (result["models"]?.arrayValue ?? []).map(Model.init)
        cachePath = result["cachePath"]?.stringValue ?? ""
    }

    private func commitEdits(id: UUID) async throws {
        guard let transcript = document?.transcript else { throw StoreError.invalidResult }
        let edits = segmentDrafts
        guard !edits.isEmpty else { return }
        let batch: [JSONValue] = edits.keys.sorted().map { index in
            .object(["segmentIndex": .number(Double(index)), "text": .string(edits[index]!)])
        }
        let result = try await run(["operation": .string("edit"), "transcript": transcript, "edits": .array(batch)], id: id)
        guard let updated = result["transcript"] else { throw StoreError.invalidResult }
        try replaceTranscript(updated)
        segmentDrafts = [:]
        updateUnsavedState()
    }

    private func replaceTranscript(_ transcript: JSONValue?) throws {
        guard let transcript, let document else { throw StoreError.invalidResult }
        self.document = TranscriptionDocument(source: document.source, transcript: transcript, captionPreferences: preferences)
        committedUnsavedChanges = true
        updateUnsavedState()
        invalidateCaptions()
    }

    private func buildCaptions(id: UUID) async throws {
        guard let transcript = document?.transcript else { throw StoreError.invalidResult }
        if !trimEnd.isEmpty && Double(trimEnd) == nil { throw StoreError.invalidTrim }
        let requestedPreferences = preferences
        let result = try await run(["operation": .string("captions"), "transcript": transcript,
                                    "captionOptions": requestedPreferences, "captionWindow": requestedPreferences], id: id)
        guard preferences == requestedPreferences else {
            invalidateCaptions()
            throw StoreError.changedCaptionSettings
        }
        guard let srt = result["srt"]?.stringValue, let vtt = result["webVTT"]?.stringValue,
              let cues = result["cues"]?.arrayValue else { throw StoreError.invalidResult }
        self.cues = cues
        subtitleSRT = srt
        subtitleVTT = vtt
        captionsNeedRefresh = false
        previewTime = min(previewTime, previewDuration)
    }

    private func invalidateCaptions() { captionsNeedRefresh = true; cues = []; subtitleSRT = ""; subtitleVTT = "" }

    private func updateUnsavedState() {
        hasUnsavedChanges = document != nil && (committedUnsavedChanges || hasPendingTextEdits
            || (savedCaptionPreferences.map { preferences != $0 } ?? false))
    }

    private func protectDestination(_ url: URL) throws {
        let resolved = url.standardizedFileURL.resolvingSymlinksInPath()
        for source in protectedMediaURLs + [sourceURL].compactMap({ $0 }) {
            if resolved == source.standardizedFileURL.resolvingSymlinksInPath() { throw StoreError.sourceDestination }
            if TranscriptionDocument.sameFile(url, source) { throw StoreError.sourceDestination }
        }
    }

    private func confirmReplacement() -> Bool {
        let alert = NSAlert()
        alert.messageText = "Replace the current transcript?"
        alert.informativeText = hasUnsavedChanges ? "This transcript has unsaved changes. Save it first to keep them." : "The currently displayed transcript will be replaced."
        alert.addButton(withTitle: "Cancel")
        alert.addButton(withTitle: "Replace Transcript")
        return alert.runModal() == .alertSecondButtonReturn
    }

    private enum StoreError: LocalizedError {
        case invalidResult, changedSource, invalidTrim, sourceDestination, changedCaptionSettings
        var errorDescription: String? {
            switch self {
            case .invalidResult: return "The transcription helper returned an incomplete result."
            case .changedSource: return "The source recording changed. Select the original recording or recognize it again."
            case .changedCaptionSettings: return "Caption settings changed. Build the caption preview again."
            case .invalidTrim: return "Enter a valid trim end in seconds, or leave it empty."
            case .sourceDestination: return "Choose a destination separate from the image, recording and video files."
            }
        }
    }
}
