import AppKit
import SwiftUI
import SparkleBridge

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
        _ = ATIVStartUpdater()
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

    @AppStorage("appearance") private var appearance = "system"

    var body: some Scene {
        WindowGroup("ATIV", id: "main") {
            ContentView()
                .preferredColorScheme(appearance == "dark" ? .dark : appearance == "light" ? .light : nil)
                .frame(minWidth: 720, idealWidth: 1040, minHeight: 520, idealHeight: 720)
        }
        .commands {
            CommandGroup(after: .appInfo) {
                Button("Check for Updates…") {
                    if !ATIVCheckForUpdates() {
                        let alert = NSAlert()
                        alert.messageText = "Updates are unavailable in this build"
                        alert.informativeText = "Install an official ATIV release to receive verified updates."
                        alert.runModal()
                    }
                }
            }
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
