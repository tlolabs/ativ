using System.Diagnostics;
using System.Text.Json;
namespace ATIV.Services;
public static class UpdateClient
{
    public static async Task<JsonElement> RunAsync(string command)
    {
        var start = new ProcessStartInfo(Path.Combine(AppContext.BaseDirectory, "ativ-update.exe")) {
            UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true
        };
        start.ArgumentList.Add(command);
        using var process = Process.Start(start) ?? throw new IOException("Could not start the update service.");
        var output = process.StandardOutput.ReadToEndAsync();
        var error = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();
        if (process.ExitCode != 0) throw new IOException(await error);
        using var json = JsonDocument.Parse(await output);
        return json.RootElement.Clone();
    }
    public static void InstallPortable(JsonElement download)
    {
        var directory = Path.Combine(Path.GetTempPath(), "ativ-portable-helper-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        var helper = Path.Combine(directory,"ativ-portable-update.exe");
        File.Copy(Path.Combine(AppContext.BaseDirectory,"ativ-portable-update.exe"),helper,false);
        var start = new ProcessStartInfo(helper) { UseShellExecute=false };
        start.ArgumentList.Add(download.GetProperty("path").GetString()!);
        start.ArgumentList.Add(download.GetProperty("sha256").GetString()!);
        start.ArgumentList.Add(AppContext.BaseDirectory);
        start.ArgumentList.Add(Environment.ProcessId.ToString());
        start.ArgumentList.Add(download.GetProperty("target").GetString()!);
        start.ArgumentList.Add(download.GetProperty("version").GetString()!);
        _ = Process.Start(start) ?? throw new IOException("Cannot start the portable update helper.");
    }
}
