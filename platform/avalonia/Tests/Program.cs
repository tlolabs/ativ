using ATIV.Models;
using ATIV.Services;
using ATIV.ViewModels;

static void Assert(bool condition, string message) { if (!condition) throw new Exception(message); }
var engine = new FakeEngine();
var updates = new FakeUpdates();
var settings = new Preferences();
var saved = 0;
var model = new MainViewModel(engine, updates, settings, _ => saved++);
await model.LoadAsync();
var legacyFile = Path.GetTempFileName();
try
{
    File.WriteAllText(legacyFile, "[General]\nappearance=dark\nbitrate=192k\nfps=60\nautomatic_updates=false\n");
    var migrated = Preferences.LoadLegacyLinux(legacyFile);
    Assert(migrated.Appearance == "Dark" && migrated.Bitrate == "192k" && migrated.Fps == 60 && !migrated.AutomaticUpdates, "Linux INI migration lost settings");
}
finally { File.Delete(legacyFile); }
Assert(model.Platforms.SequenceEqual(["YouTube", "Instagram"]), "platform choices lost");
Assert(model.Aspects.SequenceEqual(["16:9", "1:1"]), "aspect choices lost");
Assert(model.Resolutions.Count == 1 && model.SelectedPreset?.Width == 1920, "resolution choices lost");
model.SelectedAspect = "1:1";
Assert(model.SelectedPreset?.Width == 1080, "aspect selection lost");
model.SelectedPlatform = "Instagram";
Assert(model.SelectedPreset?.Height == 1920, "platform selection lost");
model.SetImage("/tmp/artwork.ppm");
await model.SetAudioAsync("/tmp/audio.wav");
Assert(model.OutputPath == "/tmp/artwork.mp4" && model.Duration == "00:01", "path suggestion or duration failed");
Assert(model.CanRender, "valid media cannot render");
model.SetOutput(model.ImagePath);
Assert(!model.CanRender, "source overwrite must be rejected");
model.SetOutput("/tmp/output.mp4");
Assert(model.BeginUpdate() && !model.CanRender && !model.BeginUpdate(), "update lock must prevent render and duplicate update");
model.EndUpdate();
Assert(model.CanRender, "render must recover after update");
var render = model.RenderOrCancelAsync();
await engine.RenderStarted.Task;
Assert(model.IsRendering && model.RenderLabel == "Stop Video Creation", "render state not exposed");
await model.RenderOrCancelAsync();
await render;
Assert(engine.Cancelled && !model.IsRendering && saved > 0 && model.Status.Contains("preserved"), "safe cancellation or preference save failed");
Assert(!model.IsUpdating, "update lock leaked");
Assert(new PlatformUpdates().Enabled == !OperatingSystem.IsMacOS(), "platform production update boundary changed");
Console.WriteLine("Shared presentation tests passed: presets, paths, validation, update exclusion, render cancellation and reference isolation.");

sealed class FakeEngine : IMediaEngine
{
    private readonly TaskCompletionSource renderExit = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public readonly TaskCompletionSource RenderStarted = new(TaskCreationOptions.RunContinuationsAsynchronously);
    public bool Cancelled { get; private set; }
    public Task<IReadOnlyList<Preset>> GetPresetsAsync() => Task.FromResult<IReadOnlyList<Preset>>([
        new("YouTube", "16:9", 1920, 1080), new("YouTube", "1:1", 1080, 1080), new("Instagram", "9:16", 1080, 1920)]);
    public Task<double?> ProbeAsync(string audio) => Task.FromResult<double?>(1);
    public Task PreviewAsync(string image, string output, int width, int height, bool flipHorizontal, bool flipVertical) => Task.CompletedTask;
    public async Task RenderAsync(string image, string audio, string output, Preset preset, string bitrate, int fps, bool flipHorizontal, bool flipVertical, Action<EngineEvent> onEvent)
    { RenderStarted.SetResult(); await renderExit.Task; throw new OperationCanceledException("Video creation was stopped. The previous output was preserved."); }
    public Task CancelAsync() { Cancelled = true; renderExit.SetResult(); return Task.CompletedTask; }
    public Task CancelPreviewAsync() => Task.CompletedTask;
}
sealed class FakeUpdates : IPlatformUpdates
{
    public bool Enabled => true;
    public bool CanInstallDirectly => true;
    public Task<UpdateInfo> CheckAsync(bool manual) => Task.FromResult(new UpdateInfo(false, null));
    public Task<string> InstallOrDownloadAsync() => Task.FromResult("done");
}
