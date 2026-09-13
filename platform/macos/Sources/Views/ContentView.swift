import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @StateObject private var store = RenderStore()

    var body: some View {
        VStack(spacing: 0) {
            HSplitView {
                ScrollView { controls.padding(24) }
                    .frame(minWidth: 470, idealWidth: 560)
                preview
                    .frame(minWidth: 350, maxWidth: .infinity, maxHeight: .infinity)
            }
            Divider()
            statusBar
        }
        .navigationTitle("A.V.I.D.")
        .task { store.start() }
        .alert("A.V.I.D. couldn’t complete the operation", isPresented: Binding(get: { store.errorMessage != nil }, set: { if !$0 { store.errorMessage = nil } })) {
            Button("OK") { store.errorMessage = nil }
        } message: { Text(store.errorMessage ?? "Unknown error") }
        .onReceive(NotificationCenter.default.publisher(for: .avidChooseImage)) { _ in store.chooseImage() }
        .onReceive(NotificationCenter.default.publisher(for: .avidChooseAudio)) { _ in store.chooseAudio() }
        .onReceive(NotificationCenter.default.publisher(for: .avidChooseOutput)) { _ in store.chooseOutput() }
        .onReceive(NotificationCenter.default.publisher(for: .avidStartRender)) { _ in if store.canRender { store.render() } }
    }

    private var controls: some View {
        VStack(alignment: .leading, spacing: 20) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Create a video").font(.largeTitle.bold())
                Text("Combine one image with an audio recording for social media distribution.").foregroundStyle(.secondary)
            }

            GroupBox("Source media") {
                VStack(spacing: 12) {
                    FileSelectionRow(title: "Image", systemImage: "photo", url: store.imageURL, action: store.chooseImage, onDrop: store.setImage)
                    Divider()
                    FileSelectionRow(title: "Audio", systemImage: "waveform", url: store.audioURL, detail: store.duration.map(durationText), action: store.chooseAudio, onDrop: store.setAudio)
                }.padding(8)
            }

            GroupBox("Format") {
                VStack(spacing: 12) {
                    FormatRow(label: "Outlet") {
                        Picker("Outlet", selection: $store.selectedPlatform) { ForEach(store.platforms, id: \.self) { Text($0) } }
                            .labelsHidden().onChange(of: store.selectedPlatform) { _ in store.selectionChanged() }
                    }
                    FormatRow(label: "Aspect ratio") {
                        Picker("Aspect ratio", selection: $store.selectedAspect) { ForEach(store.aspects, id: \.self) { Text($0) } }
                            .labelsHidden().onChange(of: store.selectedAspect) { _ in store.selectionChanged() }
                    }
                    FormatRow(label: "Resolution") {
                        Picker("Resolution", selection: $store.selectedPreset) { ForEach(store.resolutions) { Text($0.resolution).tag(Optional($0)) } }
                            .labelsHidden().onChange(of: store.selectedPreset) { _ in store.previewOptionsChanged() }
                    }
                    FormatRow(label: "Audio bitrate") {
                        TextField("Audio bitrate", text: $store.bitrate).frame(width: 110).accessibilityHint("Enter a value such as 128k")
                    }
                    FormatRow(label: "Frame rate") {
                        TextField("Frame rate", value: $store.fps, format: .number).frame(width: 110).accessibilityLabel("Frames per second")
                    }
                }.padding(8)
            }

            GroupBox("Image options") {
                HStack(spacing: 20) {
                    Toggle("Flip horizontally", isOn: $store.flipHorizontal).onChange(of: store.flipHorizontal) { _ in store.previewOptionsChanged() }
                    Toggle("Flip vertically", isOn: $store.flipVertical).onChange(of: store.flipVertical) { _ in store.previewOptionsChanged() }
                }.padding(8)
            }

            GroupBox("Destination") {
                FileSelectionRow(title: "MP4 video", systemImage: "film", url: store.outputURL, action: store.chooseOutput, onDrop: { store.outputURL = $0 })
                    .padding(8)
            }

            if store.isRendering {
                Button(role: .destructive, action: store.cancel) { Label("Stop Video Creation", systemImage: "stop.fill").frame(maxWidth: .infinity) }
                    .controlSize(.large)
            } else {
                Button(action: store.render) { Label("Create Video", systemImage: "play.fill").frame(maxWidth: .infinity) }
                    .buttonStyle(.borderedProminent).controlSize(.large).disabled(!store.canRender)
                    .help("Create an MP4 video (⌘Return)")
            }
        }
    }

    private var preview: some View {
        VStack(spacing: 16) {
            Text("Preview").font(.title2.bold())
            ZStack {
                RoundedRectangle(cornerRadius: 14).fill(.quaternary)
                if let image = store.previewImage {
                    Image(nsImage: image).resizable().scaledToFit().padding(18).accessibilityLabel("Video frame preview")
                } else {
                    VStack(spacing: 10) {
                        Image(systemName: "photo.on.rectangle").font(.system(size: 42)).foregroundStyle(.secondary)
                        Text("Choose an image").font(.headline)
                        Text("A styled frame preview will appear here.").foregroundStyle(.secondary)
                    }.accessibilityElement(children: .combine)
                }
            }.frame(maxWidth: 440, maxHeight: 440)
            if let preset = store.selectedPreset { Text("\(preset.aspect) · \(preset.resolution)").foregroundStyle(.secondary) }
            DisclosureGroup("Diagnostics", isExpanded: $store.showDiagnostics) {
                ScrollView { Text(store.diagnostics.joined(separator: "\n")).font(.system(.caption, design: .monospaced)).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading) }
                    .frame(height: 110)
            }.padding(.horizontal)
        }.padding(24)
    }

    private var statusBar: some View {
        VStack(spacing: 6) {
            if store.isRendering { ProgressView(value: store.progress).accessibilityLabel("Video creation progress").accessibilityValue("\(Int(store.progress * 100)) percent") }
            Text(store.status).font(.callout).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
        }.padding(.horizontal, 16).padding(.vertical, 10)
    }

    private func durationText(_ seconds: Double) -> String {
        let total = Int(seconds.rounded())
        return String(format: "%d:%02d", total / 60, total % 60)
    }
}

private struct FormatRow<Content: View>: View {
    let label: String
    let content: Content

    init(label: String, @ViewBuilder content: () -> Content) {
        self.label = label
        self.content = content()
    }

    var body: some View {
        HStack {
            Text(label).frame(width: 110, alignment: .leading)
            content
            Spacer(minLength: 0)
        }
    }
}

private struct FileSelectionRow: View {
    let title: String
    let systemImage: String
    let url: URL?
    var detail: String?
    let action: () -> Void
    let onDrop: (URL) -> Void

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: systemImage).font(.title2).foregroundStyle(.secondary).frame(width: 28)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(.headline)
                Text(url?.lastPathComponent ?? "Nothing selected").foregroundStyle(url == nil ? .secondary : .primary).lineLimit(1).truncationMode(.middle)
                if let detail { Text(detail).font(.caption).foregroundStyle(.secondary) }
            }
            Spacer()
            Button("Choose…", action: action).accessibilityLabel("Choose \(title.lowercased())")
        }
        .contentShape(Rectangle())
        .onDrop(of: [UTType.fileURL.identifier], isTargeted: nil) { providers in
            guard let provider = providers.first else { return false }
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                let data = item as? Data
                if let data, let url = URL(dataRepresentation: data, relativeTo: nil) { DispatchQueue.main.async { onDrop(url) } }
            }
            return true
        }
    }
}
