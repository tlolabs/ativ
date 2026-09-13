using ATIV.Models;
using ATIV.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;
using Windows.Storage.Pickers;

namespace ATIV;

public sealed partial class MainWindow : Window
{
    private readonly EngineClient engine = new();
    private IReadOnlyList<Preset> presets = [];
    private bool rendering;
    private bool loadingPresets;
    private int previewGeneration;

    public MainWindow()
    {
        InitializeComponent();
        SystemBackdrop = new MicaBackdrop();
        AppWindow.Resize(new Windows.Graphics.SizeInt32(1100, 760));
        Activated += async (_, _) => { if (presets.Count == 0 && !loadingPresets) await LoadPresetsAsync(); };
    }

    private async Task LoadPresetsAsync()
    {
        loadingPresets = true;
        try
        {
            presets = await engine.GetPresetsAsync();
            PlatformBox.ItemsSource = presets.Select(item => item.Platform).Distinct().ToList();
            PlatformBox.SelectedIndex = 0;
            StatusText.Text = "Choose an image and audio recording.";
        }
        catch (Exception error) { ShowError(error.Message); }
        finally { loadingPresets = false; }
    }

    private async void ChooseImage(object sender, RoutedEventArgs args)
    {
        var file = await PickFileAsync([".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"]);
        if (file is null) return;
        SetImage(file.Path);
    }

    private async void ChooseAudio(object sender, RoutedEventArgs args)
    {
        var file = await PickFileAsync([".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"]);
        if (file is null) return;
        await SetAudioAsync(file.Path);
    }

    private async void ChooseOutput(object sender, RoutedEventArgs args)
    {
        var picker = new FileSavePicker { SuggestedFileName = SuggestedOutputName() ?? "video" };
        picker.FileTypeChoices.Add("MP4 video", [".mp4"]);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this));
        var file = await picker.PickSaveFileAsync();
        if (file is null) return;
        OutputPath.Text = file.Path;
        UpdateRenderEnabled();
    }

    private async Task<StorageFile?> PickFileAsync(IEnumerable<string> types)
    {
        var picker = new FileOpenPicker();
        foreach (var type in types) picker.FileTypeFilter.Add(type);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, WinRT.Interop.WindowNative.GetWindowHandle(this));
        return await picker.PickSingleFileAsync();
    }

    private void SetImage(string path)
    {
        ImagePath.Text = path;
        SuggestOutput(path);
        UpdateRenderEnabled();
        _ = RefreshPreviewAsync();
    }

    private async Task SetAudioAsync(string path)
    {
        AudioPath.Text = path;
        SuggestOutput(path);
        DurationText.Text = "Reading duration…";
        UpdateRenderEnabled();
        try
        {
            var duration = await engine.ProbeAsync(path);
            DurationText.Text = duration is null ? "Duration unavailable" : TimeSpan.FromSeconds(duration.Value).ToString(duration >= 3600 ? @"h\:mm\:ss" : @"mm\:ss");
        }
        catch (Exception error) { DurationText.Text = "Duration unavailable"; ShowError(error.Message); }
    }

    private void SuggestOutput(string source)
    {
        if (!string.IsNullOrWhiteSpace(OutputPath.Text)) return;
        OutputPath.Text = Path.ChangeExtension(source, ".mp4");
    }

    private string? SuggestedOutputName()
    {
        var source = string.IsNullOrWhiteSpace(AudioPath.Text) ? ImagePath.Text : AudioPath.Text;
        return string.IsNullOrWhiteSpace(source) ? null : Path.GetFileNameWithoutExtension(source);
    }

    private void PlatformChanged(object sender, SelectionChangedEventArgs args)
    {
        if (PlatformBox.SelectedItem is not string platform) return;
        AspectBox.ItemsSource = presets.Where(item => item.Platform == platform).Select(item => item.Aspect).Distinct().ToList();
        AspectBox.SelectedIndex = 0;
    }

    private void AspectChanged(object sender, SelectionChangedEventArgs args)
    {
        if (PlatformBox.SelectedItem is not string platform || AspectBox.SelectedItem is not string aspect) return;
        ResolutionBox.ItemsSource = presets.Where(item => item.Platform == platform && item.Aspect == aspect).ToList();
        ResolutionBox.SelectedIndex = 0;
        _ = RefreshPreviewAsync();
    }

    private void PreviewOptionsChanged(object sender, RoutedEventArgs args) => _ = RefreshPreviewAsync();
    private void PreviewOptionsChanged(object sender, SelectionChangedEventArgs args) => _ = RefreshPreviewAsync();

    private async Task RefreshPreviewAsync()
    {
        if (string.IsNullOrWhiteSpace(ImagePath.Text) || ResolutionBox.SelectedItem is not Preset preset) return;
        var generation = ++previewGeneration;
        var ratio = (double)preset.Width / preset.Height;
        var width = ratio >= 1 ? 360 : Math.Max(2, ((int)(360 * ratio)) & ~1);
        var height = ratio >= 1 ? Math.Max(2, ((int)(360 / ratio)) & ~1) : 360;
        var output = Path.Combine(Path.GetTempPath(), $"ativ-preview-{Guid.NewGuid():N}.png");
        try
        {
            await engine.PreviewAsync(ImagePath.Text, output, width, height, FlipHorizontal.IsChecked == true, FlipVertical.IsChecked == true);
            if (generation != previewGeneration) { File.Delete(output); return; }
            var file = await StorageFile.GetFileFromPathAsync(output);
            using var stream = await file.OpenReadAsync();
            var bitmap = new BitmapImage();
            await bitmap.SetSourceAsync(stream);
            File.Delete(output);
            if (generation != previewGeneration) return;
            PreviewImage.Source = bitmap;
            PreviewCaption.Text = $"{preset.Aspect} · {preset.Resolution}";
        }
        catch (Exception error) { if (generation == previewGeneration) ShowError(error.Message); }
    }

    private async void RenderOrCancel(object sender, RoutedEventArgs args)
    {
        if (rendering)
        {
            RenderButton.IsEnabled = false;
            StatusText.Text = "Stopping safely…";
            await engine.CancelAsync();
            return;
        }
        if (ResolutionBox.SelectedItem is not Preset preset) return;
        rendering = true;
        RenderButton.Content = "Stop Video Creation";
        RenderButton.IsEnabled = true;
        RenderProgress.Value = 0;
        StatusText.Text = "Preparing video…";
        try
        {
            await engine.RenderAsync(ImagePath.Text, AudioPath.Text, OutputPath.Text, preset, BitrateBox.Text, Math.Max(1, (int)FpsBox.Value), FlipHorizontal.IsChecked == true, FlipVertical.IsChecked == true, item => DispatcherQueue.TryEnqueue(() => ApplyEvent(item)));
            RenderProgress.Value = 1;
            StatusText.Text = $"Video saved as {Path.GetFileName(OutputPath.Text)}.";
        }
        catch (OperationCanceledException error) { StatusText.Text = error.Message; }
        catch (Exception error) { ShowError(error.Message); StatusText.Text = "The previous output was preserved."; }
        finally
        {
            rendering = false;
            RenderButton.Content = "Create Video";
            RenderButton.IsEnabled = true;
            UpdateRenderEnabled();
        }
    }

    private void ApplyEvent(EngineEvent item)
    {
        if (item.Event == "progress")
        {
            RenderProgress.Value = Math.Clamp(item.Fraction ?? 0, 0, 1);
            StatusText.Text = item.EtaSeconds is double eta
                ? $"Creating video — {RenderProgress.Value:P0} — about {TimeSpan.FromSeconds(eta):m\\:ss} remaining"
                : $"Creating video — {RenderProgress.Value:P0}";
        }
        else if (item.Event == "stage") StatusText.Text = StageText(item.Stage);
        else if (item.Event == "error" && item.Message is not null) ShowError(item.Message);
    }

    private static string StageText(string? stage) => stage switch
    {
        "validating" => "Checking files…", "probing" => "Reading media…", "compositing" => "Building frame…",
        "encoding" => "Creating video…", "publishing" => "Saving completed video…", "complete" => "Complete", _ => "Working…"
    };

    private void UpdateRenderEnabled() => RenderButton.IsEnabled = rendering || (!string.IsNullOrWhiteSpace(ImagePath.Text) && !string.IsNullOrWhiteSpace(AudioPath.Text) && !string.IsNullOrWhiteSpace(OutputPath.Text) && ResolutionBox.SelectedItem is Preset);
    private void ShowError(string message) { ErrorBar.Message = message; ErrorBar.IsOpen = true; }

    private void MediaDragOver(object sender, DragEventArgs args)
    {
        if (args.DataView.Contains(StandardDataFormats.StorageItems)) args.AcceptedOperation = DataPackageOperation.Copy;
    }

    private async void ImageDrop(object sender, DragEventArgs args)
    {
        if (!args.DataView.Contains(StandardDataFormats.StorageItems)) return;
        var file = (await args.DataView.GetStorageItemsAsync()).OfType<StorageFile>().FirstOrDefault();
        if (file is null) return;
        var extension = Path.GetExtension(file.Path).ToLowerInvariant();
        if (new[] { ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus" }.Contains(extension)) await SetAudioAsync(file.Path);
        else SetImage(file.Path);
    }
}
