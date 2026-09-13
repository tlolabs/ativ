import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }
}

extension Notification.Name {
    static let avidChooseImage = Notification.Name("avidChooseImage")
    static let avidChooseAudio = Notification.Name("avidChooseAudio")
    static let avidChooseOutput = Notification.Name("avidChooseOutput")
    static let avidStartRender = Notification.Name("avidStartRender")
}

@main
struct AVIDApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup("A.V.I.D.", id: "main") {
            ContentView()
                .frame(minWidth: 900, idealWidth: 1040, minHeight: 620, idealHeight: 720)
        }
        .commands {
            CommandGroup(replacing: .newItem) { }
            CommandMenu("Media") {
                Button("Choose Image…") { NotificationCenter.default.post(name: .avidChooseImage, object: nil) }
                    .keyboardShortcut("i", modifiers: [.command])
                Button("Choose Audio…") { NotificationCenter.default.post(name: .avidChooseAudio, object: nil) }
                    .keyboardShortcut("a", modifiers: [.command])
                Button("Choose Output…") { NotificationCenter.default.post(name: .avidChooseOutput, object: nil) }
                    .keyboardShortcut("s", modifiers: [.command, .shift])
                Divider()
                Button("Create Video") { NotificationCenter.default.post(name: .avidStartRender, object: nil) }
                    .keyboardShortcut(.return, modifiers: [.command])
            }
        }

        Settings { SettingsView() }
    }
}
