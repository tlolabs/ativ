using ATIV.Models;

namespace ATIV.Services;

public interface IMediaEngine
{
    Task<IReadOnlyList<Preset>> GetPresetsAsync();
    Task<double?> ProbeAsync(string audio);
    Task PreviewAsync(string image, string output, int width, int height, bool flipHorizontal, bool flipVertical);
    Task RenderAsync(string image, string audio, string output, Preset preset, string bitrate, int fps, bool flipHorizontal, bool flipVertical, Action<EngineEvent> onEvent);
    Task CancelAsync();
    Task CancelPreviewAsync();
}
