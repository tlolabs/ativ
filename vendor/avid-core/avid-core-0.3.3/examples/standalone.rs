//! cargo run --example standalone -- IMAGE AUDIO OUTPUT.mp4
use avid_core::*;
fn main() -> Result<()> {
    let paths: Vec<_> = std::env::args_os().skip(1).collect();
    if paths.len() != 3 {
        return Err(Error::InvalidInput(
            "Usage: standalone IMAGE AUDIO OUTPUT.mp4".into(),
        ));
    }
    let cancellation = CancellationToken::default();
    let tools = MediaTools::discover(ToolDiscovery::default(), &cancellation)?;
    Renderer::new(tools).render(
        &RenderRequest {
            input: Input::Single {
                image: paths[0].clone().into(),
                audio: paths[1].clone().into(),
            },
            settings: RenderSettings::default(),
            output: paths[2].clone().into(),
            protected_paths: vec![],
        },
        &cancellation,
        &(),
    )?;
    Ok(())
}
