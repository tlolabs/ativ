using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using ATIV.Models;
using ATIV.Services;

namespace ATIV.ViewModels;

public sealed class MainViewModel : INotifyPropertyChanged
{
    private readonly IMediaEngine engine;
    private readonly IPlatformUpdates updates;
    private readonly Preferences preferences;
    private readonly Action<Preferences> persist;
    private IReadOnlyList<Preset> presets = [];
    private int previewGeneration;
    private int audioGeneration;
    private string? previewKey;
    private string? previewPath;
    private string imagePath = "", audioPath = "", outputPath = "", duration = "No audio selected";
    private string status = "Loading media engine…", error = "", previewCaption = "Choose an image to see a styled preview.";
    private string bitrate;
    private int fps;
    private bool flipHorizontal, flipVertical, isRendering, isUpdating;
    private double progress;
    private string appearance;
    private bool automaticUpdates;
    private string? selectedPlatform, selectedAspect;
    private Preset? selectedPreset;
    public event PropertyChangedEventHandler? PropertyChanged;
    public event Action<string>? PreviewReady;

    public MainViewModel(IMediaEngine engine, IPlatformUpdates updates, Preferences preferences, Action<Preferences>? persist = null)
    {
        this.engine = engine; this.updates = updates; this.preferences = preferences; this.persist = persist ?? (settings => settings.Save());
        bitrate = preferences.Bitrate; fps = preferences.Fps; appearance = preferences.Appearance; automaticUpdates = preferences.AutomaticUpdates;
    }
    public ObservableCollection<string> Platforms { get; } = [];
    public ObservableCollection<string> Aspects { get; } = [];
    public ObservableCollection<Preset> Resolutions { get; } = [];
    public string ImagePath { get => imagePath; private set { imagePath = value; Changed(); Changed(nameof(CanRender)); } }
    public string AudioPath { get => audioPath; private set { audioPath = value; Changed(); Changed(nameof(CanRender)); } }
    public string OutputPath { get => outputPath; private set { outputPath = value; Changed(); Changed(nameof(CanRender)); } }
    public string Duration { get => duration; private set { duration = value; Changed(); } }
    public string Status { get => status; private set { status = value; Changed(); } }
    public string Error { get => error; private set { error = value; Changed(); } }
    public string PreviewCaption { get => previewCaption; private set { previewCaption = value; Changed(); } }
    public double Progress { get => progress; private set { progress = value; Changed(); } }
    public string Bitrate { get => bitrate; set { bitrate = value; Changed(); } }
    public int Fps { get => fps; set { fps = Math.Clamp(value, 1, 240); Changed(); } }
    public bool FlipHorizontal { get => flipHorizontal; set { flipHorizontal = value; Changed(); _ = RefreshPreviewAsync(); } }
    public bool FlipVertical { get => flipVertical; set { flipVertical = value; Changed(); _ = RefreshPreviewAsync(); } }
    public string Appearance { get => appearance; set { appearance = value; Changed(); } }
    public bool AutomaticUpdates { get => automaticUpdates; set { automaticUpdates = value; Changed(); } }
    public bool IsRendering { get => isRendering; private set { isRendering = value; Changed(); Changed(nameof(CanRender)); Changed(nameof(RenderLabel)); } }
    public bool IsUpdating { get => isUpdating; private set { isUpdating = value; Changed(); Changed(nameof(CanRender)); } }
    public bool CanCheckUpdates => updates.Enabled;
    public bool CanRender => IsRendering || (!IsUpdating && SelectedPreset is not null && !string.IsNullOrWhiteSpace(ImagePath) && !string.IsNullOrWhiteSpace(AudioPath) &&
        !string.IsNullOrWhiteSpace(OutputPath) && !OutputPath.Equals(ImagePath, StringComparison.OrdinalIgnoreCase) && !OutputPath.Equals(AudioPath, StringComparison.OrdinalIgnoreCase));
    public string RenderLabel => IsRendering ? "Stop Video Creation" : "Create Video";
    public string? SelectedPlatform
    {
        get => selectedPlatform;
        set
        {
            if (selectedPlatform == value) return;
            selectedPlatform = value; Changed();
            Aspects.Clear();
            foreach (var aspect in presets.Where(p => p.Platform == value).Select(p => p.Aspect).Distinct()) Aspects.Add(aspect);
            SelectedAspect = Aspects.FirstOrDefault();
        }
    }
    public string? SelectedAspect
    {
        get => selectedAspect;
        set
        {
            if (selectedAspect == value) return;
            selectedAspect = value; Changed();
            Resolutions.Clear();
            foreach (var preset in presets.Where(p => p.Platform == SelectedPlatform && p.Aspect == value)) Resolutions.Add(preset);
            SelectedPreset = Resolutions.FirstOrDefault();
        }
    }
    public Preset? SelectedPreset
    {
        get => selectedPreset;
        set { if (selectedPreset == value) return; selectedPreset = value; Changed(); Changed(nameof(CanRender)); _ = RefreshPreviewAsync(); }
    }
    private void Changed([CallerMemberName] string? name = null) => PropertyChanged?.Invoke(this, new(name));

    public async Task LoadAsync()
    {
        try
        {
            presets = await engine.GetPresetsAsync();
            Platforms.Clear();
            foreach (var platform in presets.Select(p => p.Platform).Distinct()) Platforms.Add(platform);
            SelectedPlatform = Platforms.FirstOrDefault();
            Status = "Choose an image and audio recording.";
            if (Environment.GetEnvironmentVariable("ATIV_SMOKE_REPORT") is { } report && presets.Count == 27)
                File.WriteAllText(report, "{\"startup\":true,\"presets\":27}");
        }
        catch (Exception e) { ShowError(e.Message); Status = "The ATIV media engine is missing or damaged. Reinstall the application."; }
    }
    public void SetImage(string path)
    {
        if (IsRendering || IsUpdating) return;
        ImagePath = path; SuggestOutput(path); _ = RefreshPreviewAsync();
    }
    public async Task SetAudioAsync(string path)
    {
        if (IsRendering || IsUpdating) return;
        var generation = ++audioGeneration;
        AudioPath = path; SuggestOutput(path); Duration = "Reading duration…";
        try
        {
            var seconds = await engine.ProbeAsync(path);
            if (generation == audioGeneration) Duration = seconds is null ? "Duration unavailable" : TimeSpan.FromSeconds(seconds.Value).ToString(seconds >= 3600 ? @"h\:mm\:ss" : @"mm\:ss");
        }
        catch (Exception e) { if (generation == audioGeneration) { Duration = "Duration unavailable"; ShowError(e.Message); } }
    }
    public void SetOutput(string path) { if (!IsRendering && !IsUpdating) OutputPath = path; }
    public string SuggestedOutputName => Path.GetFileNameWithoutExtension(string.IsNullOrWhiteSpace(AudioPath) ? ImagePath : AudioPath) is { Length: > 0 } s ? s : "video";
    private void SuggestOutput(string source)
    {
        if (!string.IsNullOrWhiteSpace(OutputPath)) return;
        OutputPath = Path.GetExtension(source).Equals(".mp4", StringComparison.OrdinalIgnoreCase)
            ? Path.Combine(Path.GetDirectoryName(source) ?? "", Path.GetFileNameWithoutExtension(source) + "-video.mp4") : Path.ChangeExtension(source, ".mp4");
    }
    public async Task RefreshPreviewAsync()
    {
        if (IsRendering || string.IsNullOrWhiteSpace(ImagePath) || SelectedPreset is not { } preset) return;
        var ratio = (double)preset.Width / preset.Height;
        var width = ratio >= 1 ? 360 : Math.Max(2, ((int)(360 * ratio)) & ~1);
        var height = ratio >= 1 ? Math.Max(2, ((int)(360 / ratio)) & ~1) : 360;
        var key = $"{ImagePath}|{width}x{height}|{FlipHorizontal}|{FlipVertical}";
        if (key == previewKey && previewPath is not null) return;
        previewKey = key;
        var generation = ++previewGeneration;
        var output = Path.Combine(Path.GetTempPath(), $"ativ-preview-{Guid.NewGuid():N}.png");
        try
        {
            await engine.PreviewAsync(ImagePath, output, width, height, FlipHorizontal, FlipVertical);
            if (generation != previewGeneration) return;
            PreviewReady?.Invoke(output);
            if (previewPath is not null) TryDelete(previewPath);
            previewPath = output; PreviewCaption = $"{preset.Aspect} · {preset.Resolution}";
        }
        catch (Exception e) { if (generation == previewGeneration) ShowError(e.Message); }
        finally { if (generation != previewGeneration) TryDelete(output); }
    }
    public async Task RenderOrCancelAsync()
    {
        if (IsRendering) { Status = "Stopping safely…"; await engine.CancelAsync(); return; }
        if (!CanRender || SelectedPreset is not { } preset) return;
        SavePreferences(); IsRendering = true; Progress = 0; Status = "Preparing video…";
        try
        {
            ++previewGeneration; await engine.CancelPreviewAsync();
            var ui = SynchronizationContext.Current;
            await engine.RenderAsync(ImagePath, AudioPath, OutputPath, preset, Bitrate, Fps, FlipHorizontal, FlipVertical,
                item => { if (ui is null) ApplyEvent(item); else ui.Post(_ => ApplyEvent(item), null); });
            Progress = 1; Status = $"Video saved as {Path.GetFileName(OutputPath)}.";
        }
        catch (OperationCanceledException e) { Status = e.Message; }
        catch (Exception e) { ShowError(e.Message); Status = "The previous output was preserved."; }
        finally { IsRendering = false; }
    }
    private void ApplyEvent(EngineEvent item)
    {
        if (item.Event == "progress")
        {
            Progress = Math.Clamp(item.Fraction ?? 0, 0, 1);
            Status = item.EtaSeconds is double eta ? $"Creating video — {Progress:P0} — about {TimeSpan.FromSeconds(eta):m\\:ss} remaining" : $"Creating video — {Progress:P0}";
        }
        else if (item.Event == "stage") Status = item.Stage switch
        {
            "validating" => "Checking files…", "probing" => "Reading media…", "compositing" => "Building frame…",
            "encoding" => "Creating video…", "publishing" => "Saving completed video…", "complete" => "Complete", _ => "Working…"
        };
        else if (item.Event == "error" && item.Message is not null) ShowError(item.Message);
    }
    public bool BeginUpdate()
    {
        if (!updates.Enabled || IsUpdating || IsRendering) return false;
        IsUpdating = true; return true;
    }
    public Task<UpdateInfo> CheckUpdateAsync(bool manual) => updates.CheckAsync(manual);
    public async Task<string> InstallUpdateAsync() { if (IsRendering) throw new InvalidOperationException("Finish your export before installing."); SavePreferences(); return await updates.InstallOrDownloadAsync(); }
    public void EndUpdate() => IsUpdating = false;
    public void SavePreferences()
    {
        preferences.Bitrate = Bitrate; preferences.Fps = Fps; preferences.Appearance = Appearance; preferences.AutomaticUpdates = AutomaticUpdates;
        try { persist(preferences); } catch (IOException e) { ShowError(e.Message); }
    }
    public void ShowError(string message) => Error = message;
    public void ClearError() => Error = "";
    public void Cleanup() { if (previewPath is not null) TryDelete(previewPath); }
    private static void TryDelete(string path) { try { File.Delete(path); } catch (IOException) { } }
}
