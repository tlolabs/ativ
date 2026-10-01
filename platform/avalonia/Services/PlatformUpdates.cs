using System.Diagnostics;
using System.Text.Json;

namespace ATIV.Services;

public interface IPlatformUpdates
{
    bool Enabled { get; }
    bool CanInstallDirectly { get; }
    Task<UpdateInfo> CheckAsync(bool manual);
    Task<string> InstallOrDownloadAsync();
}

public sealed record UpdateInfo(bool Available, string? Version);

public sealed class PlatformUpdates : IPlatformUpdates
{
    public bool Enabled => !OperatingSystem.IsMacOS(); // Reference Mac must never enter the production update channel.
    public bool CanInstallDirectly => OperatingSystem.IsWindows() ||
        (OperatingSystem.IsLinux() && !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("APPIMAGE")));

    public async Task<UpdateInfo> CheckAsync(bool manual)
    {
        if (!Enabled) throw new InvalidOperationException("Updates are unavailable in the internal reference build.");
        var json = await UpdateClient.RunAsync(manual ? "check" : "check-auto");
        return new(json.GetProperty("available").GetBoolean(), json.TryGetProperty("version", out var version) ? version.GetString() : null);
    }

    public async Task<string> InstallOrDownloadAsync()
    {
        if (!Enabled) throw new InvalidOperationException("Reference builds cannot install updates.");
        if (OperatingSystem.IsWindows())
        {
            var download = await UpdateClient.RunAsync("download");
            UpdateClient.InstallPortable(download);
            return "Installation started. ATIV will close to complete the update.";
        }
        if (CanInstallDirectly)
        {
            await UpdateClient.RunAsync("install-appimage");
            return "Update installed. Restart ATIV to use it.";
        }
        var manual = await UpdateClient.RunAsync("download");
        var path = manual.GetProperty("path").GetString() ?? throw new IOException("Downloaded update path is missing.");
        var start = new ProcessStartInfo("xdg-open") { UseShellExecute = false };
        start.ArgumentList.Add(Path.GetDirectoryName(path) ?? path);
        _ = Process.Start(start) ?? throw new IOException("Could not open the downloaded update location.");
        return "Verified update downloaded. Close ATIV and replace the old AppImage manually.";
    }
}
