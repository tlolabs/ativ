use std::process::Command;

fn engine(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_ativ-engine"))
        .args(args)
        .output()
        .unwrap()
}

#[test]
fn exact_presets_json_and_order() {
    let result = engine(&["presets"]);
    assert!(result.status.success());
    assert_eq!(
        String::from_utf8(result.stdout).unwrap(),
        include_str!("fixtures/presets.ndjson").replace("\r\n", "\n")
    );
    assert!(result.stderr.is_empty());
}

#[test]
fn version_is_the_application_package_version() {
    let result = engine(&["version"]);
    assert!(result.status.success());
    assert_eq!(
        String::from_utf8(result.stdout).unwrap(),
        format!(
            "ativ-engine {}\n",
            option_env!("ATIV_VERSION").unwrap_or(env!("CARGO_PKG_VERSION"))
        )
    );
}

#[test]
fn invalid_command_retains_error_shape_and_exit_status() {
    let result = engine(&["/private/not-a-command"]);
    assert_eq!(result.status.code(), Some(1));
    assert_eq!(
        String::from_utf8(result.stdout).unwrap(),
        "{\"event\":\"error\",\"code\":\"invalid_input\",\"message\":\"Unknown command. Run ativ-engine help.\"}\n"
    );
}

#[test]
fn invalid_render_mode_is_rejected_before_media_discovery() {
    let result = engine(&["render", "--render-mode", "typo"]);
    assert_eq!(result.status.code(), Some(1));
    assert!(
        String::from_utf8(result.stdout)
            .unwrap()
            .contains("--render-mode must be simple or current.")
    );
}

#[test]
fn build_info_reports_the_resolved_core() {
    let result = engine(&["build-info"]);
    assert!(result.status.success());
    let info: serde_json::Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(info["avid_core"]["version"], "0.3.0");
    assert_eq!(
        info["avid_core"]["revision"],
        "3fb68807bc7c350359e1634b32af477ea3042c16"
    );
    assert_eq!(info["avid_core"]["source"], ativ_core::CORE_SOURCE);
}
