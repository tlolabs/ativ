using System.Runtime.InteropServices;
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
    [DllImport("user32.dll")]
    private static extern uint GetDpiForWindow(nint hwnd);

    private readonly EngineClient engine = new();
    private IReadOnlyList<Preset> presets = [];
    private bool rendering;
    private bool loadingPresets;
    private int previewGeneration;
    private int audioGeneration;
    private readonly Preferences preferences = Preferences.Load();
    private readonly DispatcherTimer updateTimer = new() { Interval = TimeSpan.FromHours(24) };
    private bool updateBusy;
    private bool closeAfterRender;


    public MainWindow()
    {
        InitializeComponent();
        SystemBackdrop = new MicaBackdrop();
        AppWindow.SetIcon(Path.Combine(AppContext.BaseDirectory, "Assets", "ATIV.ico"));
        if (File.Exists(Path.Combine(AppContext.BaseDirectory,"development-build"))) Title = "ATIV Development";
        ApplyAppearance();
        BitrateBox.Text = preferences.Bitrate;
        FpsBox.Value = preferences.Fps;
        updateTimer.Tick += async (_, _) => { if (preferences.AutomaticUpdates) await CheckUpdatesAsync(false); };
        RootGrid.Loaded += async (_, _) => { updateTimer.Start(); if (preferences.AutomaticUpdates) await CheckUpdatesAsync(false); };
        AppWindow.Closing += async (_, e) => {
            if (rendering) { e.Cancel = true; closeAfterRender = true; await engine.CancelAsync(); }
            else { SavePreferences(); updateTimer.Stop(); }
        };

        var dpi = GetDpiForWindow(WinRT.Interop.WindowNative.GetWindowHandle(this));
        var scale = dpi > 0 ? dpi / 96.0 : 1.0;
        var display = Microsoft.UI.Windowing.DisplayArea.GetFromWindowId(AppWindow.Id, Microsoft.UI.Windowing.DisplayAreaFallback.Primary);
        AppWindow.Resize(new Windows.Graphics.SizeInt32((int)Math.Min(1100*scale,display.WorkArea.Width-40*scale), (int)Math.Min(760*scale,display.WorkArea.Height-40*scale)));
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
            if (Environment.GetEnvironmentVariable("ATIV_SMOKE_REPORT") is { } report && presets.Count == 27)
                File.WriteAllText(report, "{\"startup\":true,\"presets\":27}");
        }
        catch (Exception error) { ShowError(error.Message); }
        finally { loadingPresets = false; }
    }

    private async void ChooseImage(object sender, RoutedEventArgs args)
    {
        if (rendering) return;
        var file = await PickFileAsync(["*"]);
        if (file is null) return;
        SetImage(file.Path);
    }

    private async void ChooseAudio(object sender, RoutedEventArgs args)
    {
        if (rendering) return;
        var file = await PickFileAsync(["*"]);
        if (file is null) return;
        await SetAudioAsync(file.Path);
    }

    private async void ChooseOutput(object sender, RoutedEventArgs args)
    {
        if (rendering) return;
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
        if (rendering) return;
        ImagePath.Text = path;
        SuggestOutput(path);
        UpdateRenderEnabled();
        _ = RefreshPreviewAsync();
    }

    private async Task SetAudioAsync(string path)
    {
        if (rendering) return;
        var generation = ++audioGeneration;
        AudioPath.Text = path;
        SuggestOutput(path);
        DurationText.Text = "Reading duration…";
        UpdateRenderEnabled();
        try
        {
            var duration = await engine.ProbeAsync(path);
            if (generation != audioGeneration) return;
            DurationText.Text = duration is null ? "Duration unavailable" : TimeSpan.FromSeconds(duration.Value).ToString(duration >= 3600 ? @"h\:mm\:ss" : @"mm\:ss");
        }
        catch (Exception error) { DurationText.Text = "Duration unavailable"; ShowError(error.Message); }
    }

    private void SuggestOutput(string source)
    {
        if (!string.IsNullOrWhiteSpace(OutputPath.Text)) return;
        if (string.Equals(Path.GetExtension(source), ".mp4", StringComparison.OrdinalIgnoreCase))
        {
            var dir = Path.GetDirectoryName(source);
            var stem = Path.GetFileNameWithoutExtension(source);
            OutputPath.Text = Path.Combine(dir ?? "", $"{stem}-video.mp4");
            return;
        }
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
            var bitmap = new BitmapImage();
            using (var stream = await file.OpenReadAsync()) { await bitmap.SetSourceAsync(stream); }
            File.Delete(output);
            if (generation != previewGeneration) return;
            PreviewImage.Source = bitmap;
            PreviewCaption.Text = $"{preset.Aspect} · {preset.Resolution}";
        }
        catch (Exception error) { if (generation == previewGeneration) ShowError(error.Message); }
        finally { try { File.Delete(output); } catch (IOException) { } }
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
        if (string.Equals(OutputPath.Text, ImagePath.Text, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(OutputPath.Text, AudioPath.Text, StringComparison.OrdinalIgnoreCase))
        {
            ShowError("The output destination must be separate from the image and audio source files.");
            return;
        }
        SavePreferences();
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
            if (closeAfterRender) Close();
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

    private void UpdateRenderEnabled() => RenderButton.IsEnabled = rendering || (
        !string.IsNullOrWhiteSpace(ImagePath.Text) &&
        !string.IsNullOrWhiteSpace(AudioPath.Text) &&
        !string.IsNullOrWhiteSpace(OutputPath.Text) &&
        !string.Equals(OutputPath.Text, ImagePath.Text, StringComparison.OrdinalIgnoreCase) &&
        !string.Equals(OutputPath.Text, AudioPath.Text, StringComparison.OrdinalIgnoreCase) &&
        ResolutionBox.SelectedItem is Preset);

    private void ShowError(string message)
    {
        if (ErrorBar.IsOpen && ErrorBar.Message == message) return;
        ErrorBar.Message = message;
        ErrorBar.IsOpen = true;
    }

    private void ApplyAppearance() => RootGrid.RequestedTheme = preferences.Appearance switch {
        "Dark" => ElementTheme.Dark, "Light" => ElementTheme.Light, _ => ElementTheme.Default
    };
    private void SavePreferences() {
        preferences.Bitrate = BitrateBox.Text;
        preferences.Fps = double.IsFinite(FpsBox.Value) ? (int)FpsBox.Value : 30;
        try { preferences.Save(); } catch (IOException error) { ShowError(error.Message); }
    }
    private async void OpenPreferences(object sender, RoutedEventArgs args) {
        var appearance = new ComboBox { Header = "Appearance", ItemsSource = new[] { "System", "Light", "Dark" }, SelectedItem = preferences.Appearance };
        var updates = new CheckBox { Content = "Automatically check for updates", IsChecked = preferences.AutomaticUpdates };
        var panel = new StackPanel { Spacing = 16 }; panel.Children.Add(appearance); panel.Children.Add(updates);
        var dialog = new ContentDialog { Title = "Preferences", Content = panel, PrimaryButtonText = "Save", CloseButtonText = "Cancel", XamlRoot = RootGrid.XamlRoot };
        if (await dialog.ShowAsync() == ContentDialogResult.Primary) {
            preferences.Appearance = appearance.SelectedItem as string ?? "System";
            preferences.AutomaticUpdates = updates.IsChecked == true; ApplyAppearance(); SavePreferences();
        }
    }
    private async void ShowAbout(object sender, RoutedEventArgs args) {
        await new ContentDialog { Title = "ATIV", Content = "Artwork + Tracks Into Video\nLocal media processing. No telemetry.\n" + typeof(App).Assembly.GetName().Version, CloseButtonText = "Close", XamlRoot = RootGrid.XamlRoot }.ShowAsync();
    }
    private async void CheckForUpdates(object sender, RoutedEventArgs args) => await CheckUpdatesAsync(true);
    private async Task CheckUpdatesAsync(bool manual) {
        if (updateBusy || rendering) return;
        updateBusy = true;
        try {
            var result = await UpdateClient.RunAsync("check");
            if (!result.GetProperty("available").GetBoolean()) {
                if (manual) await new ContentDialog { Title = "ATIV is up to date", CloseButtonText = "OK", XamlRoot = RootGrid.XamlRoot }.ShowAsync();
                return;
            }
            var dialog = new ContentDialog { Title = "ATIV " + result.GetProperty("version").GetString() + " is available", Content = "Download and install the verified update?", PrimaryButtonText = "Install", CloseButtonText = "Later", XamlRoot = RootGrid.XamlRoot };
            if (await dialog.ShowAsync() != ContentDialogResult.Primary || rendering) return;
            var download = await UpdateClient.RunAsync("download");
            if (rendering) { ShowError("Update downloaded. Finish your export before installing."); return; }
            var installer = download.GetProperty("path").GetString()!;
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(installer) { UseShellExecute = true });
            Close();
        } catch (Exception error) { if (manual) ShowError(error.Message); }
        finally { updateBusy = false; }
    }

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
        if (file.ContentType.StartsWith("audio/", StringComparison.OrdinalIgnoreCase) || new[] { ".wav", ".mp3", ".m4a", ".m4b", ".aac", ".flac", ".ogg", ".oga", ".opus", ".aif", ".aiff", ".wma", ".alac" }.Contains(extension)) await SetAudioAsync(file.Path);
        else SetImage(file.Path);
    }
}
