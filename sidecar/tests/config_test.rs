use elspeth_sidecar::config::{Config, SecurityMode};
use std::path::PathBuf;

#[test]
fn test_config_from_file_sidecar_mode() {
    let config_str = r#"
mode = "sidecar"
socket_path = "/run/sidecar/auth.sock"
session_key_path = "/run/sidecar/.session"
appuser_uid = 1000
grant_ttl_secs = 60
log_level = "debug"
"#;

    let config: Config = toml::from_str(config_str).unwrap();

    assert_eq!(config.mode, SecurityMode::Sidecar);
    assert_eq!(config.socket_path, PathBuf::from("/run/sidecar/auth.sock"));
    assert_eq!(config.session_key_path, PathBuf::from("/run/sidecar/.session"));
    assert_eq!(config.appuser_uid, 1000);
    assert_eq!(config.grant_ttl_secs, 60);
    assert_eq!(config.log_level, "debug");
}

#[test]
fn test_config_missing_mode_fails() {
    let config_str = r#"
socket_path = "/run/sidecar/auth.sock"
session_key_path = "/run/sidecar/.session"
appuser_uid = 1000
grant_ttl_secs = 60
log_level = "debug"
"#;

    let result = toml::from_str::<Config>(config_str);
    assert!(result.is_err(), "Config without mode should fail");
}

#[test]
fn test_config_standalone_mode() {
    let config_str = r#"
mode = "standalone"
socket_path = "/tmp/dev.sock"
session_key_path = "/tmp/dev.session"
appuser_uid = 1000
grant_ttl_secs = 60
log_level = "debug"
"#;

    let config: Config = toml::from_str(config_str).unwrap();
    assert_eq!(config.mode, SecurityMode::Standalone);

    // Note: validate() will emit warning log when called
    // In real usage, Config::load() calls validate()
}

#[test]
fn test_config_grant_ttl_conversion() {
    let config_str = r#"
mode = "sidecar"
socket_path = "/run/sidecar/auth.sock"
session_key_path = "/run/sidecar/.session"
appuser_uid = 1000
grant_ttl_secs = 120
log_level = "info"
"#;

    let config: Config = toml::from_str(config_str).unwrap();
    assert_eq!(config.grant_ttl().as_secs(), 120);
}
