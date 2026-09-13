import AppKit
import UniformTypeIdentifiers

enum PanelService {
    static func chooseImage() -> URL? {
        chooseFile(title: "Choose an image", extensions: ["png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff"])
    }
    static func chooseAudio() -> URL? {
        chooseFile(title: "Choose an audio recording", extensions: ["wav", "mp3", "m4a", "aac", "flac", "ogg", "opus"])
    }
    static func chooseOutput(suggested: URL?) -> URL? {
        let panel = NSSavePanel()
        panel.title = "Save video"
        panel.allowedContentTypes = [.mpeg4Movie]
        panel.canCreateDirectories = true
        panel.nameFieldStringValue = suggested?.lastPathComponent ?? "video.mp4"
        if let suggested { panel.directoryURL = suggested.deletingLastPathComponent() }
        return panel.runModal() == .OK ? panel.url : nil
    }
    private static func chooseFile(title: String, extensions: [String]) -> URL? {
        let panel = NSOpenPanel()
        panel.title = title
        panel.allowedContentTypes = extensions.compactMap { UTType(filenameExtension: $0) }
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        return panel.runModal() == .OK ? panel.url : nil
    }
}
