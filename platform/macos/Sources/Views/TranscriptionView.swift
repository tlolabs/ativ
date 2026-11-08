import SwiftUI

struct TranscriptionView: View {
    @ObservedObject var store: TranscriptionStore
    @State private var expanded = false
    @State private var modelManagerExpanded = false
    @State private var removeConfirmation = false

    var body: some View {
        GroupBox {
            DisclosureGroup(isExpanded: $expanded) {
                if store.capability.isSupported {
                    VStack(alignment: .leading, spacing: 14) {
                        recognition
                        Divider()
                        modelManager
                        if store.hasTranscript {
                            Divider()
                            editor
                            Divider()
                            captions
                        }
                        operationStatus
                    }
                    .padding(.top, 12)
                } else {
                    Text(store.capability.reason)
                        .foregroundStyle(.secondary)
                        .padding(.top, 12)
                }
            } label: {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Transcript and Captions").font(.headline)
                    if !expanded {
                        Text(store.hasTranscript ? "Transcript available\(store.hasUnsavedChanges ? " · unsaved changes" : "")" : "Optional local transcription and subtitle sidecars")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            .padding(8)
        }
        .task { store.loadCatalog() }
        .alert("Transcription couldn’t complete the operation", isPresented: Binding(get: { store.errorMessage != nil }, set: { if !$0 { store.errorMessage = nil } })) {
            Button("OK") { store.errorMessage = nil }
        } message: { Text(store.errorMessage ?? "Unknown error") }
        .confirmationDialog("Remove the managed model installation?", isPresented: $removeConfirmation) {
            Button("Remove Model", role: .destructive) { store.modelOperation("remove") }
            Button("Cancel", role: .cancel) { }
        } message: {
            Text("This removes the shared AVID installation and partial downloads. ATIV and EnCAP use this cache. Removal reports busy while a model is in use; your original imported folder is preserved.")
        }
    }

    private var recognition: some View {
        VStack(alignment: .leading, spacing: 10) {
            Picker("Recognition model", selection: $store.selectedModelID) {
                ForEach(store.recognitionModels) { model in
                    Text(model.name).tag(model.id)
                }
            }
            .disabled(store.isBusy || store.models.isEmpty)
            .onChange(of: store.selectedModelID) { modelID in store.managedModelID = modelID }
            TextField("Language code (empty for automatic)", text: $store.language)
                .textFieldStyle(.roundedBorder)
                .accessibilityLabel("Recognition and alignment language")
                .disabled(store.isBusy)
            Text("Full Whisper large-v3 is the quality default. Recognition runs offline with installed files. Model downloads are anonymous; your audio stays on this Mac.")
                .font(.caption).foregroundStyle(.secondary)
            if store.selectedModelID == "qwen3-asr-1.7b-4bit" {
                Text("Qwen recognition returns untimed text. Install the forced aligner and run Realign Text before exporting timed captions.")
                    .font(.caption)
            }
            if let model = store.selectedModel, !model.installed {
                Text("Install or import \(model.name) in Model Management first.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            HStack {
                Button("Transcribe Audio", action: store.transcribe).disabled(!store.canTranscribe)
                Button("Open Transcript…", action: store.openDocument).disabled(store.isBusy)
            }
            if store.sourceURL == nil { Text("Choose an audio recording in Source Media.").font(.caption).foregroundStyle(.secondary) }
        }
    }

    private var modelManager: some View {
        DisclosureGroup("Model Management", isExpanded: $modelManagerExpanded) {
            VStack(alignment: .leading, spacing: 10) {
                Picker("Manage model", selection: $store.managedModelID) {
                    ForEach(store.models) { model in Text(model.name).tag(model.id) }
                }
                .disabled(store.isBusy || store.models.isEmpty)
                Button("Refresh Installed Models", action: store.refreshCatalog).disabled(store.isBusy)
                if let model = store.managedModel {
                    Text("Download: \(bytes(model.bytes)) · Disk use: \(bytes(model.diskBytes))\(model.partialBytes > 0 ? " · Partial: \(bytes(model.partialBytes))" : "")")
                        .font(.caption)
                    Text(model.installed ? "Installed; inference verifies all files before loading." : "No complete managed installation.")
                        .font(.caption).foregroundStyle(.secondary)
                    Text("Download size is not runtime memory or an accuracy ranking.").font(.caption).foregroundStyle(.secondary)
                    if !model.timingLanguages.isEmpty {
                        DisclosureGroup("Supported timing languages") {
                            Text(model.timingLanguages.joined(separator: ", "))
                                .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                        }
                    }
                    HStack {
                        Button("Install / Resume") { store.modelOperation("install") }
                        Button("Verify") { store.modelOperation("verify") }.disabled(!model.installed)
                        Button("Import Folder…", action: store.chooseModelFolder)
                    }
                    .disabled(store.isBusy)
                    Button("Remove Model…", role: .destructive) { removeConfirmation = true }
                        .disabled(store.isBusy || (model.diskBytes == 0 && model.partialBytes == 0))
                    DisclosureGroup("Model license and notice") {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(model.value["license"]?["identifier"]?.stringValue ?? "").font(.caption.bold())
                            Text(model.notice).font(.caption).textSelection(.enabled)
                            if let path = model.value["license"]?["url"]?.stringValue,
                               let url = URL(string: path), url.scheme == "https" {
                                Link("Model license", destination: url).font(.caption)
                            }
                        }
                    }
                }
                if !store.cachePath.isEmpty {
                    Text("Shared cache: \(store.cachePath)").font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                }
            }.padding(.top, 8)
        }
    }

    private var editor: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Transcript").font(.headline)
                Spacer()
                if store.hasUnsavedChanges { Text("Unsaved changes").font(.caption).foregroundStyle(.secondary) }
            }
            if !store.sourceMatchesDocument {
                Text("This transcript belongs to another recording. Its text is retained. Select the matching source before realignment or saving.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if !store.segments.isEmpty {
                Picker("Segment", selection: $store.selectedSegment) {
                    ForEach(store.segments.indices, id: \.self) { index in
                        Text("\(index + 1): \((store.segments[index]["text"]?.stringValue ?? "").prefix(55))").tag(index)
                    }
                }.disabled(store.isBusy)
                TextEditor(text: Binding(get: { store.selectedSegmentText }, set: store.updateSelectedText))
                    .font(.body)
                    .frame(minHeight: 110, maxHeight: 170)
                    .border(.quaternary)
                    .accessibilityLabel("Editable transcript segment")
                    .disabled(store.isBusy)
            } else { Text("No speech segments found.").foregroundStyle(.secondary) }
            Text("Text corrections remove the affected word timings. Realign Text restores timing without recognizing the words again.")
                .font(.caption).foregroundStyle(.secondary)
            HStack {
                Button("Apply Corrections", action: store.applyEdits).disabled(store.isBusy || !store.hasPendingTextEdits)
                Button("Save Transcript…", action: store.saveDocument).disabled(store.isBusy || !store.sourceMatchesDocument)
            }
            if !store.alignmentModels.isEmpty {
                Picker("Alignment model", selection: $store.alignmentModelID) {
                    ForEach(store.alignmentModels) { model in Text(model.name).tag(model.id) }
                }.disabled(store.isBusy)
            }
            Button("Realign Text", action: store.align).disabled(!store.canAlign)
            Text(store.hasWordTiming ? "Complete word timings available." : "Word timing is missing or text corrections are pending.")
                .font(.caption).foregroundStyle(.secondary)
            if let provenance = store.document?.transcript["provenance"] {
                Text("Recognition: \(provenance["modelID"]?.stringValue ?? "unknown") · Alignment: \(store.document?.transcript["alignmentProvenance"]?["modelID"]?.stringValue ?? "recognizer timing or unaligned")")
                    .font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
            }
        }
    }

    private var captions: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Timed Caption Preview").font(.headline)
            Stepper("Maximum words: \(store.maximumWords)", value: $store.maximumWords, in: 1...30)
            Stepper("Maximum characters: \(store.maximumCharacters)", value: $store.maximumCharacters, in: 8...200)
            numericField("Maximum duration (s)", value: $store.maximumDuration)
            numericField("Maximum pause (s)", value: $store.maximumPause)
            DisclosureGroup("Caption trim and timeline") {
                VStack(alignment: .leading, spacing: 8) {
                    numericField("Source start (s)", value: $store.trimStart)
                    TextField("Source end (s), empty for full length", text: $store.trimEnd)
                    numericField("Timeline start (s)", value: $store.timelineStart)
                    Text("These settings project subtitle times only. They do not trim the MP4 or alter original word timing.")
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(.top, 8)
            }
            Button(store.captionsNeedRefresh ? "Build Caption Preview" : "Refresh Caption Preview", action: store.generateCaptions)
                .disabled(store.isBusy || !store.hasWordTiming)
            if !store.cues.isEmpty {
                highlightedPreview
                Slider(value: $store.previewTime, in: 0...store.previewDuration)
                    .accessibilityLabel("Caption preview time")
                Text(String(format: "%.2f seconds on subtitle timeline · %d cues", store.previewTime, store.cues.count))
                    .font(.caption).foregroundStyle(.secondary)
            }
            HStack {
                Button("Export SRT…") { store.exportSubtitles(webVTT: false) }
                Button("Export WebVTT…") { store.exportSubtitles(webVTT: true) }
            }.disabled(store.isBusy || !store.hasWordTiming || !store.sourceMatchesDocument)
            Text("Preview and subtitle sidecars are available. MP4 exports currently contain no burned-in or animated captions.")
                .font(.caption).foregroundStyle(.secondary)
        }
        .disabled(store.isBusy)
        .onChange(of: store.maximumWords) { _ in store.captionSettingsChanged() }
        .onChange(of: store.maximumCharacters) { _ in store.captionSettingsChanged() }
        .onChange(of: store.maximumDuration) { _ in store.captionSettingsChanged() }
        .onChange(of: store.maximumPause) { _ in store.captionSettingsChanged() }
        .onChange(of: store.trimStart) { _ in store.captionSettingsChanged() }
        .onChange(of: store.trimEnd) { _ in store.captionSettingsChanged() }
        .onChange(of: store.timelineStart) { _ in store.captionSettingsChanged() }
    }

    private var highlightedPreview: some View {
        Group {
            if let cue = store.activeCue {
                Text(highlightedText(cue)).font(.title2.bold())
            } else { Text("…").font(.title2).accessibilityLabel("No caption at this time") }
        }
        .frame(maxWidth: .infinity, minHeight: 65)
        .padding(10)
        .background(.quaternary, in: RoundedRectangle(cornerRadius: 8))
    }

    /// Locate words in Core's already joined cue text; do not reconstruct Unicode spacing.
    private func highlightedText(_ cue: JSONValue) -> AttributedString {
        let text = cue["text"]?.stringValue ?? ""
        var result = AttributedString(text)
        var searchStart = text.startIndex
        for word in cue["words"]?.arrayValue ?? [] {
            guard let token = word["text"]?.stringValue?.trimmingCharacters(in: .whitespacesAndNewlines), !token.isEmpty,
                  let range = text.range(of: token, range: searchStart..<text.endIndex) else { continue }
            searchStart = range.upperBound
            guard let start = word["startSeconds"]?.doubleValue, let end = word["endSeconds"]?.doubleValue,
                  store.previewTime >= start, store.previewTime < end,
                  let lower = AttributedString.Index(range.lowerBound, within: result),
                  let upper = AttributedString.Index(range.upperBound, within: result) else { continue }
            result[lower..<upper].foregroundColor = .accentColor
            result[lower..<upper].underlineStyle = .single
        }
        return result
    }

    private var operationStatus: some View {
        VStack(alignment: .leading, spacing: 8) {
            if store.isBusy {
                if let progress = store.progress { ProgressView(value: progress).accessibilityLabel("Transcription progress") }
                else { ProgressView().controlSize(.small) }
                Button("Cancel Operation", role: .cancel, action: store.cancel)
            }
            Text(store.status).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
        }
    }

    private func numericField(_ title: String, value: Binding<Double>) -> some View {
        HStack {
            Text(title)
            Spacer()
            TextField(title, value: value, format: .number).frame(width: 80).labelsHidden()
        }
    }

    private func bytes(_ value: Double) -> String {
        ByteCountFormatter.string(fromByteCount: Int64(max(0, min(value, Double(Int64.max / 2)))), countStyle: .file)
    }
}
