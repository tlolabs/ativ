import SwiftUI

struct SettingsView: View {
    @AppStorage("audioBitrate") private var audioBitrate = "128k"
    @AppStorage("fps") private var fps = 30

    @AppStorage("appearance") private var appearance = "system"
    @AppStorage("SUEnableAutomaticChecks") private var automaticUpdates = true

    var body: some View {
        Form {
            Picker("Appearance", selection: $appearance) {
                Text("System").tag("system")
                Text("Light").tag("light")
                Text("Dark").tag("dark")
            }
            Toggle("Automatically check for updates", isOn: $automaticUpdates)
            Text("Update checks contact GitHub. Your media stays on this computer.").font(.caption).foregroundStyle(.secondary)

            TextField("Default audio bitrate", text: $audioBitrate)
            TextField("Default frame rate", value: $fps, format: .number)
        }
        .padding(24)
        .frame(width: 380)
    }
}
