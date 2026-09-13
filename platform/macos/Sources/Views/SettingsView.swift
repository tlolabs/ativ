import SwiftUI

struct SettingsView: View {
    @AppStorage("audioBitrate") private var audioBitrate = "128k"
    @AppStorage("fps") private var fps = 30

    var body: some View {
        Form {
            TextField("Default audio bitrate", text: $audioBitrate)
            TextField("Default frame rate", value: $fps, format: .number)
        }
        .padding(24)
        .frame(width: 380)
    }
}
