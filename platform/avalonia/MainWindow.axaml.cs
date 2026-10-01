using Avalonia;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Media.Imaging;
using Avalonia.Platform.Storage;
using ATIV.Services;
using ATIV.ViewModels;

namespace ATIV;

public sealed partial class MainWindow : Window
{
    private readonly MainViewModel model = new(new EngineClient(), new PlatformUpdates(), Preferences.Load());
    private readonly System.Timers.Timer updateTimer = new(TimeSpan.FromHours(24));
    private Bitmap? previewBitmap;
    private bool closeAfterRender;
    private bool shuttingDown;
    public MainWindow()
    {
        InitializeComponent(); DataContext = model;
        Title = OperatingSystem.IsMacOS() ? "ATIV Reference — Avalonia (Internal Only)" :
            File.Exists(Path.Combine(AppContext.BaseDirectory, "development-build")) ? "ATIV Development" : "ATIV — Artwork + Tracks Into Video";
        model.PreviewReady += SetPreview;
        Opened += async (_, _) =>
        {
            ApplyAppearance(); await model.LoadAsync();
            if (model.CanCheckUpdates)
            {
                updateTimer.Elapsed += (_, _) => Avalonia.Threading.Dispatcher.UIThread.Post(async () => { if (model.AutomaticUpdates) await CheckUpdatesAsync(false); });
                updateTimer.Start();
                if (model.AutomaticUpdates) await CheckUpdatesAsync(false);
            }
        };
        Closing += OnClosing;
        KeyDown += OnKeyDown;
    }
    private void SetPreview(string path)
    {
        var next = new Bitmap(path); var previous = previewBitmap;
        PreviewImage.Source = next; previewBitmap = next; previous?.Dispose();
    }
    private async void ChooseImage(object? sender, RoutedEventArgs e)
    {
        if (model.IsRendering || model.IsUpdating) return;
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions { Title = "Choose an image", AllowMultiple = false,
            FileTypeFilter = [new FilePickerFileType("Images") { Patterns = ["*.png","*.jpg","*.jpeg","*.webp","*.bmp","*.gif","*.ppm"] }] });
        if (files.FirstOrDefault()?.TryGetLocalPath() is { } path) model.SetImage(path);
    }
    private async void ChooseAudio(object? sender, RoutedEventArgs e)
    {
        if (model.IsRendering || model.IsUpdating) return;
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions { Title = "Choose an audio recording", AllowMultiple = false,
            FileTypeFilter = [new FilePickerFileType("Audio") { Patterns = ["*.wav","*.mp3","*.m4a","*.m4b","*.aac","*.flac","*.ogg","*.oga","*.opus","*.aif","*.aiff","*.wma","*.alac"] }] });
        if (files.FirstOrDefault()?.TryGetLocalPath() is { } path) await model.SetAudioAsync(path);
    }
    private async void ChooseOutput(object? sender, RoutedEventArgs e)
    {
        if (model.IsRendering || model.IsUpdating) return;
        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions { Title = "Save video", SuggestedFileName = model.SuggestedOutputName,
            FileTypeChoices = [new FilePickerFileType("MP4 video") { Patterns = ["*.mp4"] }] });
        if (file?.TryGetLocalPath() is { } path) model.SetOutput(path);
    }
    private async void RenderOrCancel(object? sender, RoutedEventArgs e)
    {
        await model.RenderOrCancelAsync();
        if (closeAfterRender && !model.IsRendering) { closeAfterRender = false; Close(); }
    }
    private void OnClosing(object? sender, WindowClosingEventArgs e)
    {
        if (model.IsRendering)
        {
            e.Cancel = true; closeAfterRender = true; _ = CancelAndCloseAsync(); return;
        }
        if (shuttingDown) return;
        shuttingDown = true; updateTimer.Stop(); model.SavePreferences(); model.Cleanup(); previewBitmap?.Dispose();
    }
    private async Task CancelAndCloseAsync()
    {
        await model.RenderOrCancelAsync();
        if (!model.IsRendering && closeAfterRender) { closeAfterRender = false; Close(); }
    }
    private async void OnKeyDown(object? sender, KeyEventArgs e)
    {
        var command = e.KeyModifiers.HasFlag(KeyModifiers.Control) || e.KeyModifiers.HasFlag(KeyModifiers.Meta);
        if (command && e.Key == Key.I) { e.Handled = true; ChooseImage(this, new RoutedEventArgs()); }
        else if (command && e.Key == Key.O) { e.Handled = true; ChooseAudio(this, new RoutedEventArgs()); }
        else if (command && e.KeyModifiers.HasFlag(KeyModifiers.Shift) && e.Key == Key.S) { e.Handled = true; ChooseOutput(this, new RoutedEventArgs()); }
        else if (command && e.Key == Key.Enter) { e.Handled = true; await model.RenderOrCancelAsync(); }
        else if (e.Key == Key.Escape && model.IsRendering) { e.Handled = true; await model.RenderOrCancelAsync(); }
    }
    private void OnDragOver(object? sender, DragEventArgs e) => e.DragEffects = e.DataTransfer.Contains(DataFormat.File) ? DragDropEffects.Copy : DragDropEffects.None;
    private async void OnDrop(object? sender, DragEventArgs e)
    {
        if (model.IsRendering || model.IsUpdating) return;
        var path = e.DataTransfer.TryGetFiles()?.FirstOrDefault()?.TryGetLocalPath();
        if (path is null) return;
        var ext = Path.GetExtension(path).ToLowerInvariant();
        if (new[] { ".wav", ".mp3", ".m4a", ".m4b", ".aac", ".flac", ".ogg", ".oga", ".opus", ".aif", ".aiff", ".wma", ".alac" }.Contains(ext))
            await model.SetAudioAsync(path);
        else model.SetImage(path);
    }
    private void ApplyAppearance() => RequestedThemeVariant = model.Appearance switch
    {
        "Dark" => Avalonia.Styling.ThemeVariant.Dark, "Light" => Avalonia.Styling.ThemeVariant.Light, _ => Avalonia.Styling.ThemeVariant.Default
    };
    private async void ShowPreferences(object? sender, RoutedEventArgs e)
    {
        var appearance = new ComboBox { ItemsSource = new[] { "System", "Light", "Dark" }, SelectedItem = model.Appearance };
        var automatic = new CheckBox { Content = "Automatically check for updates", IsChecked = model.AutomaticUpdates, IsEnabled = model.CanCheckUpdates };
        var panel = new StackPanel { Spacing = 12, Margin = new Thickness(16), Children = { new TextBlock { Text = "Appearance" }, appearance, automatic } };
        if (await AskAsync("Preferences", panel, "Save"))
        {
            model.Appearance = appearance.SelectedItem as string ?? "System";
            model.AutomaticUpdates = model.CanCheckUpdates && automatic.IsChecked == true;
            model.SavePreferences(); ApplyAppearance();
        }
    }
    private async void ShowAbout(object? sender, RoutedEventArgs e) => await InformAsync("About ATIV", "Artwork + Tracks Into Video\nLocal media processing. No telemetry.\nVersion " + typeof(App).Assembly.GetName().Version);
    private async void ManualUpdate(object? sender, RoutedEventArgs e) => await CheckUpdatesAsync(true);
    private async Task CheckUpdatesAsync(bool manual)
    {
        if (!model.BeginUpdate()) return;
        try
        {
            var update = await model.CheckUpdateAsync(manual);
            if (!update.Available) { if (manual) await InformAsync("ATIV is up to date", "No newer build is available for this platform."); return; }
            if (await AskAsync("ATIV " + update.Version + " is available", new TextBlock { Text = model.CanCheckUpdates ? "Download and install the verified update?" : "", TextWrapping = Avalonia.Media.TextWrapping.Wrap }, model.CanCheckUpdates ? "Continue" : "Close"))
            {
                var result = await model.InstallUpdateAsync();
                if (OperatingSystem.IsWindows()) Close(); else await InformAsync("Update", result);
            }
        }
        catch (Exception error) { if (manual) model.ShowError(error.Message); }
        finally { model.EndUpdate(); }
    }
    private async Task InformAsync(string title, string message) => await AskAsync(title, new TextBlock { Text = message, TextWrapping = Avalonia.Media.TextWrapping.Wrap }, null);
    private async Task<bool> AskAsync(string title, Control content, string? accept)
    {
        var dialog = new Window { Title = title, Width = 430, MinHeight = 170, SizeToContent = SizeToContent.Height, WindowStartupLocation = WindowStartupLocation.CenterOwner };
        var yes = new Button { Content = accept ?? "Close", IsDefault = true };
        var no = new Button { Content = "Cancel", IsCancel = true, IsVisible = accept is not null };
        var buttons = new StackPanel { Orientation = Avalonia.Layout.Orientation.Horizontal, HorizontalAlignment = Avalonia.Layout.HorizontalAlignment.Right, Spacing = 8, Children = { no, yes } };
        dialog.Content = new StackPanel { Margin = new Thickness(16), Spacing = 18, Children = { content, buttons } };
        yes.Click += (_, _) => dialog.Close(true); no.Click += (_, _) => dialog.Close(false);
        return await dialog.ShowDialog<bool>(this);
    }
}
