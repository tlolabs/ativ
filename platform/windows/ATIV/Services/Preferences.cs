using System.Text.Json;
namespace ATIV.Services;
public sealed class Preferences
{
    public string Appearance { get; set; } = "System";
    public string Bitrate { get; set; } = "128k";
    public int Fps { get; set; } = 30;
    public bool AutomaticUpdates { get; set; } = true;
    private static string FilePath => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        File.Exists(Path.Combine(AppContext.BaseDirectory,"development-build")) ? "ATIV Development" : "ATIV", "preferences.json");
    public static Preferences Load() { try { return JsonSerializer.Deserialize<Preferences>(File.ReadAllText(FilePath)) ?? new(); } catch { return new(); } }
    public void Save()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(FilePath)!);
        var temp = FilePath + ".tmp";
        File.WriteAllText(temp, JsonSerializer.Serialize(this));
        File.Move(temp, FilePath, true);
    }
}
