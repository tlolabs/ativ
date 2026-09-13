import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }
}

extension Notification.Name {
    static let ativChooseImage = Notification.Name("ativChooseImage")
    static let ativChooseAudio = Notification.Name("ativChooseAudio")
    static let ativChooseOutput = Notification.Name("ativChooseOutput")
    static let ativStartRender = Notification.Name("ativStartRender")
}

@main
struct ATIVApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup("A.T.I.V.", id: "main") {
            ContentView()
                .frame(minWidth: 900, idealWidth: 1040, minHeight: 620, idealHeight: 720)
        }
        .commands {
            CommandGroup(replacing: .newItem) { }
            CommandMenu("Media") {
                Button("Choose Image…") { NotificationCenter.default.post(name: .ativChooseImage, object: nil) }
                    .keyboardShortcut("i", modifiers: [.command])
                Button("Choose Audio…") { NotificationCenter.default.post(name: .ativChooseAudio, object: nil) }
                    .keyboardShortcut("a", modifiers: [.command])
                Button("Choose Output…") { NotificationCenter.default.post(name: .ativChooseOutput, object: nil) }
                    .keyboardShortcut("s", modifiers: [.command, .shift])
                Divider()
                Button("Create Video") { NotificationCenter.default.post(name: .ativStartRender, object: nil) }
                    .keyboardShortcut(.return, modifiers: [.command])
            }
        }

        Settings { SettingsView() }
    }
}
