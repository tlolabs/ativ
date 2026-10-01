using System.Text.Json;

namespace ATIV.Services;

public sealed class Preferences
{
    public string Appearance { get; set; } = "System";
    public string Bitrate { get; set; } = "128k";
    public int Fps { get; set; } = 30;
    public bool AutomaticUpdates { get; set; } = true;

    private static bool Development => File.Exists(Path.Combine(AppContext.BaseDirectory, "development-build"));
    private static string Folder => OperatingSystem.IsLinux()
        ? Path.Combine(Environment.GetEnvironmentVariable("XDG_CONFIG_HOME") ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".config"), Development ? "ativ-development" : "ativ")
        : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), OperatingSystem.IsMacOS() ? "ATIV Reference" : Development ? "ATIV Development" : "ATIV");
    private static string FilePath => Path.Combine(Folder, "preferences.json");

    public static Preferences Load()
    {
        try
        {
            if (File.Exists(FilePath)) return JsonSerializer.Deserialize<Preferences>(File.ReadAllText(FilePath)) ?? new();
            if (OperatingSystem.IsLinux()) return LoadLegacyLinux(Path.Combine(Folder, "preferences.ini"));
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or JsonException) { }
        return new();
    }

    internal static Preferences LoadLegacyLinux(string path)
    {
        var result = new Preferences();
        if (!File.Exists(path)) return result;
        var general = false;
        foreach (var line in File.ReadLines(path))
        {
            var trimmed = line.Trim();
            if (trimmed.StartsWith('[')) { general = trimmed == "[General]"; continue; }
            if (!general) continue;
            var split = trimmed.IndexOf('=');
            if (split < 0) continue;
            var key = trimmed[..split]; var value = trimmed[(split + 1)..];
            switch (key)
            {
                case "appearance": result.Appearance = value switch { "dark" => "Dark", "light" => "Light", _ => "System" }; break;
                case "bitrate": result.Bitrate = value; break;
                case "fps" when int.TryParse(value, out var fps) && fps is >= 1 and <= 240: result.Fps = fps; break;
                case "automatic_updates": result.AutomaticUpdates = value.Equals("true", StringComparison.OrdinalIgnoreCase); break;
            }
        }
        return result;
    }

    public void Save()
    {
        Directory.CreateDirectory(Folder);
        var temp = FilePath + ".tmp";
        File.WriteAllText(temp, JsonSerializer.Serialize(this));
        File.Move(temp, FilePath, true);
    }
}
