//! Host-neutral equivalent of the EnCAP video adapter. No project archive dependency.
use avid_core::*;
fn main() -> Result<()> {
    let paths: Vec<_> = std::env::args_os().skip(1).collect();
    if paths.len() != 4 {
        return Err(Error::InvalidInput(
            "Usage: sequence ARTWORK AUDIO1 AUDIO2 OUTPUT.mp4".into(),
        ));
    }
    let token = CancellationToken::default();
    let renderer = Renderer::new(MediaTools::discover(ToolDiscovery::default(), &token)?);
    let mut clips = Vec::new();
    for (index, path) in paths[1..3].iter().enumerate() {
        let audio = std::path::PathBuf::from(path);
        let duration = renderer
            .probe_audio_duration(&audio, &token)?
            .ok_or_else(|| Error::InvalidInput("Sequence needs a known duration".into()))?;
        clips.push(Clip {
            id: index.to_string(),
            image: paths[0].clone().into(),
            audio,
            duration_seconds: duration,
        });
    }
    let state = VideoProjectState::default();
    state.validate_schema()?;
    let timeline = Timeline::select(
        &clips,
        &state.export_settings.selected_chapter_ids,
        state.export_settings.selection_initialized,
    )?;
    renderer.render(
        &RenderRequest {
            input: Input::Timeline(timeline),
            settings: state.export_settings.render_settings()?,
            output: paths[3].clone().into(),
            protected_paths: vec![],
        },
        &token,
        &(),
    )?;
    Ok(())
}
