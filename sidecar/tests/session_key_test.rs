use std::fs;
use std::os::unix::fs::PermissionsExt;
use tempfile::TempDir;

// Helper to create test config
fn test_config(session_key_path: &std::path::Path) -> elspeth_sidecar::config::Config {
    elspeth_sidecar::config::Config {
        mode: elspeth_sidecar::config::SecurityMode::Sidecar,
        socket_path: std::path::PathBuf::from("/tmp/test.sock"),
        session_key_path: session_key_path.to_path_buf(),
        appuser_uid: 1000,
        grant_ttl_secs: 60,
        log_level: "debug".to_string(),
    }
}

#[test]
fn test_session_key_first_call_creates_file() {
    let temp_dir = TempDir::new().unwrap();
    let session_key_path = temp_dir.path().join("session.key");
    let config = test_config(&session_key_path);

    let result = elspeth_sidecar::server::Server::load_or_init_session_key_public(&config);
    assert!(result.is_ok(), "Session key generation should succeed");

    let (session_key, returned_path) = result.unwrap();

    // Verify key length
    assert_eq!(session_key.len(), 32, "Session key should be 32 bytes");

    // Verify file exists
    assert!(session_key_path.exists(), "Session key file should exist");

    // Verify permissions (0o640)
    let metadata = fs::metadata(&session_key_path).unwrap();
    let permissions = metadata.permissions();
    let mode = permissions.mode();
    assert_eq!(
        mode & 0o777,
        0o640,
        "Session key file should have 0o640 permissions, got {:o}",
        mode & 0o777
    );

    // Verify returned path matches config
    assert_eq!(returned_path, session_key_path);
}

#[test]
fn test_session_key_second_call_reuses_key() {
    let temp_dir = TempDir::new().unwrap();
    let session_key_path = temp_dir.path().join("session.key");
    let config = test_config(&session_key_path);

    // First call creates key
    let (key1, _) = elspeth_sidecar::server::Server::load_or_init_session_key_public(&config).unwrap();

    // Second call should reload same key
    let (key2, _) = elspeth_sidecar::server::Server::load_or_init_session_key_public(&config).unwrap();

    assert_eq!(key1, key2, "Session key should be reused on second call");
}

#[test]
fn test_session_key_file_content_matches() {
    let temp_dir = TempDir::new().unwrap();
    let session_key_path = temp_dir.path().join("session.key");
    let config = test_config(&session_key_path);

    let (session_key, _) = elspeth_sidecar::server::Server::load_or_init_session_key_public(&config).unwrap();

    // Read file contents
    let file_contents = fs::read(&session_key_path).unwrap();

    assert_eq!(
        file_contents, session_key,
        "File contents should match returned session key"
    );
}

#[test]
fn test_session_key_randomness() {
    let temp_dir = TempDir::new().unwrap();

    // Generate two keys with different paths
    let path1 = temp_dir.path().join("session1.key");
    let path2 = temp_dir.path().join("session2.key");

    let config1 = test_config(&path1);
    let config2 = test_config(&path2);

    let (key1, _) = elspeth_sidecar::server::Server::load_or_init_session_key_public(&config1).unwrap();
    let (key2, _) = elspeth_sidecar::server::Server::load_or_init_session_key_public(&config2).unwrap();

    assert_ne!(
        key1, key2,
        "Independent key generation should produce different keys"
    );
}
