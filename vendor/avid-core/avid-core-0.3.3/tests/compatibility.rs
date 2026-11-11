use avid_core::*;
use serde_json::json;
fn clip(id: &str, duration: f64) -> Clip {
    Clip {
        id: id.into(),
        image: "cover.png".into(),
        audio: "track.wav".into(),
        duration_seconds: duration,
    }
}
#[test]
fn all_ativ_presets_and_defaults_are_preserved() {
    assert_eq!(PRESETS.len(), 27);
    assert_eq!(
        (PRESETS[0].platform, PRESETS[0].width, PRESETS[0].height),
        ("Instagram", 1920, 1080)
    );
    assert!(PRESETS.iter().all(|p| p.fps == 30));
    let s = RenderSettings::default();
    assert_eq!(s.composition, Composition::Fitted);
    assert_eq!(s.encoding, Encoding::Software);
    assert_eq!(s.codec, Codec::H264);
}
#[test]
fn standalone_validation_is_not_narrowed_to_encap() {
    let mut s = RenderSettings {
        fps: 240,
        audio_bitrate: "224k".into(),
        ..Default::default()
    };
    assert!(s.validate().is_ok());
    for rate in ["128k", "1m", "192000", "192000b"] {
        s.audio_bitrate = rate.into();
        assert!(s.validate().is_ok());
    }
    for rate in ["", "0k", "-1", "1.5k", "1K", "128k -y"] {
        s.audio_bitrate = rate.into();
        assert!(s.validate().is_err());
    }
    let mut s = RenderSettings::default();
    for (w, h) in [(0, 2), (3, 2), (8192, 8192), (8194, 2)] {
        s.width = w;
        s.height = h;
        assert!(s.validate().is_err());
    }
}
#[test]
fn timeline_selection_order_and_boundaries() {
    let clips = vec![clip("one", 2.0), clip("two", 3.0)];
    let t = Timeline::select(&clips, &["two".into(), "one".into()], true).unwrap();
    assert_eq!(t.clips()[0].id, "two");
    assert_eq!(clips[0].id, "one");
    assert_eq!(t.duration_seconds(), 5.0);
    assert_eq!(
        t.position(3.0).unwrap(),
        TimelinePosition {
            index: 1,
            start_seconds: 3.0,
            offset_seconds: 0.0
        }
    );
    assert_eq!(t.position(9.0).unwrap().offset_seconds, 2.0);
    assert_eq!(t.position(-1.0).unwrap().offset_seconds, 0.0);
    assert!(t.position(f64::NAN).is_none());
    assert!(Timeline::select(&clips, &[], true)
        .unwrap()
        .clips()
        .is_empty());
    assert_eq!(
        Timeline::select(&clips, &[], false).unwrap().clips().len(),
        2
    );
}
#[test]
fn timeline_rejects_ambiguous_and_invalid_inputs() {
    let clips = vec![clip("one", 2.0)];
    assert!(Timeline::select(&clips, &["missing".into()], true).is_err());
    assert!(Timeline::select(&clips, &["one".into(), "one".into()], true).is_err());
    for duration in [0.0, -1.0, f64::NAN, f64::INFINITY] {
        assert!(Timeline::new(vec![clip("one", duration)]).is_err());
    }
    assert!(Timeline::new(vec![clip("one", f64::MAX), clip("two", f64::MAX)]).is_err());
}
#[test]
fn video_state_defaults_are_compatible() {
    let state: VideoProjectState = serde_json::from_value(json!({})).unwrap();
    assert_eq!(state, VideoProjectState::default());
    state.validate_schema().unwrap();
    let settings = state.export_settings.render_settings().unwrap();
    assert_eq!(settings.composition, Composition::SquarePadded);
    assert_eq!(settings.encoding, Encoding::Software);
    assert!(!state.export_settings.selection_initialized);
    let serialized = serde_json::to_value(state).unwrap();
    assert!(serialized.get("compositions").is_none());
}
#[test]
fn unknown_metadata_and_future_compositions_round_trip() {
    let input: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/video-state.json")).unwrap();
    let state: VideoProjectState = serde_json::from_value(input.clone()).unwrap();
    let output = serde_json::to_value(&state).unwrap();
    assert_eq!(output["future_video"], input["future_video"]);
    assert_eq!(output["compositions"], input["compositions"]);
    assert_eq!(
        output["export_settings"]["future_setting"],
        input["export_settings"]["future_setting"]
    );
    assert_eq!(
        state.export_settings.selected_chapter_ids,
        vec!["second", "first"]
    );
    assert_eq!(state.export_settings.preview_quality, "high");
    let decoded: VideoProjectState = serde_json::from_value(output).unwrap();
    assert_eq!(decoded, state);
}
#[test]
fn newer_schemas_and_unknown_execution_values_are_not_silently_used() {
    let state: VideoProjectState =
        serde_json::from_value(json!({"schema_version":2,"future":true})).unwrap();
    assert!(state.validate_schema().is_err());
    let settings = VideoSettings {
        codec: "futurecodec".into(),
        ..Default::default()
    };
    assert!(settings.render_settings().is_err());
    assert_eq!(
        serde_json::to_value(settings).unwrap()["codec"],
        "futurecodec"
    );
    let mut settings = VideoSettings {
        fps: 240,
        ..Default::default()
    };
    assert!(settings.render_settings().is_err());
    settings.fps = 30;
    settings.audio_bitrate = "224k".into();
    assert!(settings.render_settings().is_err());
}

#[test]
fn complete_preset_table_matches_both_reference_implementations() {
    let expected: serde_json::Value =
        serde_json::from_str(include_str!("fixtures/ativ-presets.json")).unwrap();
    assert_eq!(serde_json::to_value(PRESETS).unwrap(), expected);
}

#[test]
fn selection_can_precede_host_source_mapping() {
    assert_eq!(
        select_clip_indices(&["one", "two"], &["two".into()], true).unwrap(),
        vec![1]
    );
    assert!(select_clip_indices(&["one", "one"], &[], false).is_err());
    // Unselected records need no media mapping or timeline validation.
    let clips = vec![clip("one", f64::NAN), clip("two", 1.0)];
    assert_eq!(
        Timeline::select(&clips, &["two".into()], true)
            .unwrap()
            .duration_seconds(),
        1.0
    );
}
