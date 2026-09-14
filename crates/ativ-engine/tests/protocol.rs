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
