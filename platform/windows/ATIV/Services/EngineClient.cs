using System.Diagnostics;
using System.Text.Json;
using ATIV.Models;

namespace ATIV.Services;

public sealed class EngineClient
{
    private readonly object gate = new();
    private Process? renderProcess;

    private static string EnginePath
    {
        get
        {
            var configured = Environment.GetEnvironmentVariable("ATIV_ENGINE_PATH");
            if (!string.IsNullOrWhiteSpace(configured)) return configured;
            var sidecar = Path.Combine(AppContext.BaseDirectory, "ativ-engine.exe");
            if (File.Exists(sidecar)) return sidecar;
            throw new FileNotFoundException("The ATIV media engine is missing. Reinstall the application.", sidecar);
        }
    }

    public async Task<IReadOnlyList<Preset>> GetPresetsAsync()
    {
        var events = await RunCaptureAsync(["presets"]);
        return events.FirstOrDefault(item => item.Event == "presets")?.Items
            ?? throw new InvalidOperationException("The media engine returned no format presets.");
    }

    public async Task<double?> ProbeAsync(string audio)
    {
        var events = await RunCaptureAsync(["probe", "--audio", audio]);
        return events.FirstOrDefault(item => item.Event == "probe")?.DurationSeconds;
    }

    public async Task PreviewAsync(string image, string output, int width, int height, bool flipHorizontal, bool flipVertical)
    {
        var arguments = new List<string> { "preview", "--image", image, "--output", output, "--width", width.ToString(), "--height", height.ToString() };
        if (flipHorizontal) arguments.Add("--flip-horizontal");
        if (flipVertical) arguments.Add("--flip-vertical");
        await RunCaptureAsync(arguments);
    }

    public async Task RenderAsync(string image, string audio, string output, Preset preset, string bitrate, int fps, bool flipHorizontal, bool flipVertical, Action<EngineEvent> onEvent)
    {
        var arguments = new List<string> {
            "render", "--image", image, "--audio", audio, "--output", output,
            "--width", preset.Width.ToString(), "--height", preset.Height.ToString(),
            "--audio-bitrate", bitrate, "--fps", fps.ToString()
        };
        if (flipHorizontal) arguments.Add("--flip-horizontal");
        if (flipVertical) arguments.Add("--flip-vertical");
        using var process = CreateProcess(arguments);
        lock (gate) renderProcess = process;
        try
        {
            process.Start();
            var stderrTask = process.StandardError.ReadToEndAsync();
            while (await process.StandardOutput.ReadLineAsync() is { } line)
            {
                if (Deserialize(line) is { } item) onEvent(item);
            }
            await process.WaitForExitAsync();
            var stderr = await stderrTask;
            if (process.ExitCode == 0) return;
            if (process.ExitCode == 130) throw new OperationCanceledException("Video creation was stopped. The previous output was preserved.");
            throw new InvalidOperationException(stderr.Split('\n', StringSplitOptions.RemoveEmptyEntries).LastOrDefault() ?? "The media engine could not finish this operation.");
        }
        finally
        {
            lock (gate) if (ReferenceEquals(renderProcess, process)) renderProcess = null;
        }
    }

    public async Task CancelAsync()
    {
        Process? process;
        lock (gate) process = renderProcess;
        if (process is { HasExited: false })
        {
            await process.StandardInput.WriteLineAsync("cancel");
            await process.StandardInput.FlushAsync();
        }
    }

    private static async Task<List<EngineEvent>> RunCaptureAsync(IEnumerable<string> arguments)
    {
        using var process = CreateProcess(arguments);
        process.Start();
        var stdoutTask = process.StandardOutput.ReadToEndAsync();
        var stderrTask = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();
        var output = await stdoutTask;
        var errorOutput = await stderrTask;
        var events = output.Split('\n', StringSplitOptions.RemoveEmptyEntries).Select(Deserialize).Where(item => item is not null).Cast<EngineEvent>().ToList();
        if (process.ExitCode == 0) return events;
        throw new InvalidOperationException(events.LastOrDefault(item => item.Event == "error")?.Message ?? errorOutput);
    }

    private static Process CreateProcess(IEnumerable<string> arguments)
    {
        var start = new ProcessStartInfo(EnginePath) {
            UseShellExecute = false,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
        };
        foreach (var argument in arguments) start.ArgumentList.Add(argument);
        return new Process { StartInfo = start, EnableRaisingEvents = true };
    }

    private static EngineEvent? Deserialize(string line)
    {
        try { return JsonSerializer.Deserialize<EngineEvent>(line); }
        catch (JsonException) { return null; }
    }
}
