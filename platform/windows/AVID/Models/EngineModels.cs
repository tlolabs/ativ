using System.Text.Json.Serialization;

namespace AVID.Models;

public sealed record Preset(
    [property: JsonPropertyName("platform")] string Platform,
    [property: JsonPropertyName("aspect")] string Aspect,
    [property: JsonPropertyName("width")] int Width,
    [property: JsonPropertyName("height")] int Height)
{
    public string Resolution => $"{Width} × {Height}";
    public override string ToString() => Resolution;
}

public sealed class EngineEvent
{
    [JsonPropertyName("event")] public string Event { get; set; } = "";
    [JsonPropertyName("code")] public string? Code { get; set; }
    [JsonPropertyName("message")] public string? Message { get; set; }
    [JsonPropertyName("stage")] public string? Stage { get; set; }
    [JsonPropertyName("duration_seconds")] public double? DurationSeconds { get; set; }
    [JsonPropertyName("elapsed_seconds")] public double? ElapsedSeconds { get; set; }
    [JsonPropertyName("fraction")] public double? Fraction { get; set; }
    [JsonPropertyName("eta_seconds")] public double? EtaSeconds { get; set; }
    [JsonPropertyName("items")] public List<Preset>? Items { get; set; }
}
