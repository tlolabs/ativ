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
}
