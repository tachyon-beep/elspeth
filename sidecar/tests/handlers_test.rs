use elspeth_sidecar::config::{Config, SecurityMode};
use elspeth_sidecar::protocol::{Request, Response};
use elspeth_sidecar::server::Server;
use tempfile::TempDir;

fn test_config(temp_dir: &TempDir) -> Config {
    Config {
        mode: SecurityMode::Sidecar,
        socket_path: temp_dir.path().join("test.sock"),
        session_key_path: temp_dir.path().join("session.key"),
        appuser_uid: 1000,
        grant_ttl_secs: 60,
        max_request_size_bytes: 1024 * 1024, // 1 MiB
        log_level: "debug".to_string(),
    }
}

fn digest(tag: u8) -> [u8; 32] {
    [tag; 32]
}

fn frame_id_bytes(tag: u8) -> [u8; 16] {
    [tag; 16]
}

#[tokio::test]
async fn test_authorize_construct_creates_grant() {
    let temp_dir = TempDir::new().unwrap();
    let config = test_config(&temp_dir);
    let server = Server::new(config).unwrap();

    let frame_id = frame_id_bytes(0x01);
    let level = 3;
    let data_digest = digest(0xAA);

    // Compute HMAC auth for request
    let request = Request::AuthorizeConstruct {
        frame_id,
        level,
        data_digest,
        auth: vec![],
    };

    let auth = server.compute_request_auth(&request);
    let request = Request::AuthorizeConstruct {
        frame_id,
        level,
        data_digest,
        auth,
    };

    let response = server.handle_request(request).await.unwrap();

    match response {
        Response::AuthorizeConstructReply {
            grant_id,
            expires_at: _,
        } => {
            assert_eq!(grant_id.len(), 16, "Grant ID should be 16 bytes");
        }
        _ => panic!("Expected AuthorizeConstructReply, got {:?}", response),
    }
}

#[tokio::test]
async fn test_authorize_construct_with_invalid_auth_fails() {
    let temp_dir = TempDir::new().unwrap();
    let config = test_config(&temp_dir);
    let server = Server::new(config).unwrap();

    let frame_id = frame_id_bytes(0x01);
    let level = 3;
    let data_digest = digest(0xAA);

    // Use invalid auth (empty)
    let request = Request::AuthorizeConstruct {
        frame_id,
        level,
        data_digest,
        auth: vec![0xDE, 0xAD, 0xBE, 0xEF],
    };

    let response = server.handle_request(request).await.unwrap();

    match response {
        Response::Error { error, reason: _ } => {
            assert!(
                error.contains("auth") || error.contains("Auth"),
                "Error should mention authentication failure, got: {}",
                error
            );
        }
        _ => panic!("Expected Error response, got {:?}", response),
    }
}

#[tokio::test]
async fn test_redeem_grant_registers_frame() {
    let temp_dir = TempDir::new().unwrap();
    let config = test_config(&temp_dir);
    let server = Server::new(config).unwrap();

    // First authorize to get grant_id
    let frame_id = frame_id_bytes(0x02);
    let level = 2;
    let data_digest = digest(0xBB);

    let auth_request = Request::AuthorizeConstruct {
        frame_id,
        level,
        data_digest,
        auth: vec![],
    };
    let auth = server.compute_request_auth(&auth_request);
    let auth_request = Request::AuthorizeConstruct {
        frame_id,
        level,
        data_digest,
        auth,
    };

    let auth_response = server.handle_request(auth_request).await.unwrap();
    let grant_id = match auth_response {
        Response::AuthorizeConstructReply {
            grant_id,
            expires_at: _,
        } => grant_id,
        _ => panic!("Expected AuthorizeConstructReply"),
    };

    // Now redeem grant
    let redeem_request = Request::RedeemGrant {
        grant_id,
        auth: vec![],
    };
    let auth = server.compute_request_auth(&redeem_request);
    let redeem_request = Request::RedeemGrant { grant_id, auth };

    let redeem_response = server.handle_request(redeem_request).await.unwrap();

    match redeem_response {
        Response::RedeemGrantReply {
            construction_ticket,
            seal: _,
            audit_id: _,
        } => {
            assert_eq!(
                construction_ticket.len(),
                32,
                "Construction ticket should be 32 bytes"
            );
        }
        _ => panic!("Expected RedeemGrantReply, got {:?}", redeem_response),
    }

    // Verify frame was registered
    let uuid_frame_id = uuid::Uuid::from_bytes(frame_id);
    assert!(
        server.is_frame_registered(uuid_frame_id),
        "Frame should be registered after grant redemption"
    );
}

#[tokio::test]
async fn test_compute_seal_for_registered_frame() {
    let temp_dir = TempDir::new().unwrap();
    let config = test_config(&temp_dir);
    let server = Server::new(config).unwrap();

    // Setup: authorize + redeem to register frame
    let frame_id = frame_id_bytes(0x03);
    let level = 4;
    let data_digest = digest(0xCC);

    let auth_request = Request::AuthorizeConstruct {
        frame_id,
        level,
        data_digest,
        auth: vec![],
    };
    let auth = server.compute_request_auth(&auth_request);
    let auth_request = Request::AuthorizeConstruct {
        frame_id,
        level,
        data_digest,
        auth,
    };
    let auth_response = server.handle_request(auth_request).await.unwrap();
    let grant_id = match auth_response {
        Response::AuthorizeConstructReply {
            grant_id,
            expires_at: _,
        } => grant_id,
        _ => panic!("Expected AuthorizeConstructReply"),
    };

    let redeem_request = Request::RedeemGrant {
        grant_id,
        auth: vec![],
    };
    let auth = server.compute_request_auth(&redeem_request);
    let redeem_request = Request::RedeemGrant { grant_id, auth };
    server.handle_request(redeem_request).await.unwrap();

    // Now compute seal for new data
    let new_digest = digest(0xDD);
    let compute_request = Request::ComputeSeal {
        frame_id,
        level: 5,
        data_digest: new_digest,
        auth: vec![],
    };
    let auth = server.compute_request_auth(&compute_request);
    let compute_request = Request::ComputeSeal {
        frame_id,
        level: 5,
        data_digest: new_digest,
        auth,
    };

    let compute_response = server.handle_request(compute_request).await.unwrap();

    match compute_response {
        Response::ComputeSealReply { seal, audit_id: _ } => {
            assert_eq!(seal.len(), 32, "Seal should be 32 bytes");
        }
        _ => panic!("Expected ComputeSealReply, got {:?}", compute_response),
    }
}

#[tokio::test]
async fn test_compute_seal_for_unregistered_frame_fails() {
    let temp_dir = TempDir::new().unwrap();
    let config = test_config(&temp_dir);
    let server = Server::new(config).unwrap();

    // Try to compute seal for frame that was never registered
    let frame_id = frame_id_bytes(0x99);
    let compute_request = Request::ComputeSeal {
        frame_id,
        level: 3,
        data_digest: digest(0xFF),
        auth: vec![],
    };
    let auth = server.compute_request_auth(&compute_request);
    let compute_request = Request::ComputeSeal {
        frame_id,
        level: 3,
        data_digest: digest(0xFF),
        auth,
    };

    let response = server.handle_request(compute_request).await.unwrap();

    match response {
        Response::Error { error, reason: _ } => {
            assert!(
                error.contains("not registered") || error.contains("unknown frame"),
                "Error should indicate frame not registered"
            );
        }
        _ => panic!("Expected Error response, got {:?}", response),
    }
}

#[tokio::test]
async fn test_verify_seal_success() {
    let temp_dir = TempDir::new().unwrap();
    let config = test_config(&temp_dir);
    let server = Server::new(config).unwrap();

    // Setup: authorize + redeem + compute seal
    let frame_id = frame_id_bytes(0x04);
    let level = 3;
    let data_digest = digest(0xEE);

    let auth_request = Request::AuthorizeConstruct {
        frame_id,
        level,
        data_digest,
        auth: vec![],
    };
    let auth = server.compute_request_auth(&auth_request);
    let auth_request = Request::AuthorizeConstruct {
        frame_id,
        level,
        data_digest,
        auth,
    };
    let auth_response = server.handle_request(auth_request).await.unwrap();
    let grant_id = match auth_response {
        Response::AuthorizeConstructReply {
            grant_id,
            expires_at: _,
        } => grant_id,
        _ => panic!("Expected AuthorizeConstructReply"),
    };

    let redeem_request = Request::RedeemGrant {
        grant_id,
        auth: vec![],
    };
    let auth = server.compute_request_auth(&redeem_request);
    let redeem_request = Request::RedeemGrant { grant_id, auth };
    server.handle_request(redeem_request).await.unwrap();

    let compute_request = Request::ComputeSeal {
        frame_id,
        level,
        data_digest,
        auth: vec![],
    };
    let auth = server.compute_request_auth(&compute_request);
    let compute_request = Request::ComputeSeal {
        frame_id,
        level,
        data_digest,
        auth,
    };
    let compute_response = server.handle_request(compute_request).await.unwrap();
    let seal = match compute_response {
        Response::ComputeSealReply { seal, audit_id: _ } => seal,
        _ => panic!("Expected ComputeSealReply"),
    };

    // Now verify the seal
    let verify_request = Request::VerifySeal {
        frame_id,
        level,
        data_digest,
        seal,
        auth: vec![],
    };
    let auth = server.compute_request_auth(&verify_request);
    let verify_request = Request::VerifySeal {
        frame_id,
        level,
        data_digest,
        seal,
        auth,
    };

    let verify_response = server.handle_request(verify_request).await.unwrap();

    match verify_response {
        Response::VerifySealReply { valid, audit_id: _ } => {
            assert!(valid, "Seal should be valid");
        }
        _ => panic!("Expected VerifySealReply, got {:?}", verify_response),
    }
}

#[tokio::test]
async fn test_oversized_request_rejected() {
    use std::io::Write;
    use std::os::unix::net::UnixStream as StdUnixStream;
    use tempfile::tempdir;

    // Create config with 1 KiB limit
    let dir = tempdir().unwrap();
    let socket_path = dir.path().join("test.sock");
    let session_key_path = dir.path().join("session.key");

    let config_content = format!(
        r#"
mode = "standalone"
socket_path = "{}"
session_key_path = "{}"
appuser_uid = {}
grant_ttl_secs = 30
max_request_size_bytes = 1024
log_level = "debug"
"#,
        socket_path.display(),
        session_key_path.display(),
        unsafe { libc::getuid() }
    );

    let config_path = dir.path().join("config.toml");
    std::fs::write(&config_path, config_content).unwrap();

    let config = elspeth_sidecar::config::Config::load(config_path.to_str().unwrap()).unwrap();
    let server = elspeth_sidecar::server::Server::new(config.clone()).unwrap();

    // Start server in background
    tokio::spawn(async move {
        server.run().await.ok();
    });

    // Wait for server to start and socket to be created
    for _ in 0..50 {
        if socket_path.exists() {
            break;
        }
        tokio::time::sleep(tokio::time::Duration::from_millis(10)).await;
    }
    assert!(socket_path.exists(), "Socket should be created");

    // Send 2 KiB request (exceeds 1 KiB limit) using blocking I/O in spawn_blocking
    let oversized_payload = vec![0x42; 2048]; // 2 KiB of 0x42 bytes
    let socket_path_for_client = socket_path.clone();

    let response = tokio::task::spawn_blocking(move || {
        let mut stream = StdUnixStream::connect(&socket_path_for_client).unwrap();
        stream.write_all(&oversized_payload).unwrap();
        stream.shutdown(std::net::Shutdown::Write).unwrap();

        // Set read timeout to avoid infinite hang
        stream
            .set_read_timeout(Some(std::time::Duration::from_secs(5)))
            .unwrap();

        // Read response (should be error)
        let mut response = Vec::new();
        std::io::Read::read_to_end(&mut stream, &mut response).unwrap();
        response
    })
    .await
    .unwrap();

    // Should receive error response (not crash/hang)
    assert!(
        !response.is_empty(),
        "Should receive error response, not hang"
    );

    // Parse CBOR response
    let resp: elspeth_sidecar::protocol::Response = ciborium::de::from_reader(&response[..]).unwrap();

    // Should be Error variant
    match resp {
        elspeth_sidecar::protocol::Response::Error { error: _, reason } => {
            assert!(
                reason.contains("exceeds maximum") || reason.contains("too large"),
                "Error should mention size limit, got: {}",
                reason
            );
        }
        _ => panic!("Expected Error response, got: {:?}", resp),
    }
}
