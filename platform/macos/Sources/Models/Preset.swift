import Foundation

struct Preset: Codable, Hashable, Identifiable {
    let platform: String
    let aspect: String
    let width: Int
    let height: Int

    var id: String { "\(platform)|\(aspect)|\(width)x\(height)" }
    var resolution: String { "\(width) × \(height)" }
}

struct EngineEvent: Decodable {
    let event: String
    let code: String?
    let message: String?
    let stage: String?
    let durationSeconds: Double?
    let elapsedSeconds: Double?
    let fraction: Double?
    let etaSeconds: Double?
    let items: [Preset]?

    enum CodingKeys: String, CodingKey {
        case event, code, message, stage, items, fraction
        case durationSeconds = "duration_seconds"
        case elapsedSeconds = "elapsed_seconds"
        case etaSeconds = "eta_seconds"
    }
}
