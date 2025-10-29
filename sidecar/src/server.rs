//! Unix socket server for daemon ↔ orchestrator IPC.

use crate::config::Config;
use crate::crypto::Secrets;
use crate::frames::RegisteredFrameTable;
use crate::grants::GrantTable;
use crate::protocol::{Request, Response};
use anyhow::{Context, Result};
use std::path::PathBuf;
use std::sync::Arc;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{UnixListener, UnixStream};
use tracing::{debug, error, info};
use uuid::Uuid;

/// Sidecar daemon server.
pub struct Server {
    config: Arc<Config>,
    secrets: Arc<Secrets>,
    grants: Arc<GrantTable>,
    frames: Arc<RegisteredFrameTable>,
    session_key: Vec<u8>,
}

impl Server {
    /// Create new server with generated secrets.
    pub fn new(config: Config) -> Result<Self> {
        let secrets = Arc::new(Secrets::generate());
        let grants = Arc::new(GrantTable::new(config.grant_ttl()));
        let frames = Arc::new(RegisteredFrameTable::new());
        let (_session_key, _session_key_path) = Self::load_or_init_session_key(&config)?;

        Ok(Self {
            config: Arc::new(config),
            secrets,
            grants,
            frames,
            session_key: _session_key,
        })
    }

    /// Run server (listens on Unix socket).
    pub async fn run(&self) -> Result<()> {
        // Remove stale socket if exists
        if self.config.socket_path.exists() {
            std::fs::remove_file(&self.config.socket_path)
                .context("Failed to remove stale socket")?;
        }

        // Bind Unix socket
        let listener = UnixListener::bind(&self.config.socket_path)
            .context("Failed to bind Unix socket")?;

        info!("Listening on {:?}", self.config.socket_path);

        // Accept connections
        loop {
            match listener.accept().await {
                Ok((stream, _addr)) => {
                    // Clone server state for spawn
                    let server = Server {
                        config: self.config.clone(),
                        secrets: self.secrets.clone(),
                        grants: self.grants.clone(),
                        frames: self.frames.clone(),
                        session_key: self.session_key.clone(),
                    };

                    tokio::spawn(async move {
                        if let Err(e) = server.handle_client(stream).await {
                            error!("Client error: {}", e);
                        }
                    });
                }
                Err(e) => {
                    error!("Accept error: {}", e);
                }
            }
        }
    }

    /// Handle single client connection.
    async fn handle_client(&self, mut stream: UnixStream) -> Result<()> {
        // TODO: SO_PEERCRED check (Phase 3)

        debug!("Client connected");

        // Read CBOR request
        let mut buffer = vec![0u8; 4096];
        let n = stream.read(&mut buffer).await?;

        if n == 0 {
            return Ok(()); // EOF
        }

        let request: Request = serde_cbor::from_slice(&buffer[..n])
            .context("Failed to parse CBOR request")?;

        debug!("Received request: {:?}", request);

        // Dispatch request (includes HMAC validation)
        let response = self.handle_request(request).await?;

        // Send response
        let response_bytes = serde_cbor::to_vec(&response)?;
        stream.write_all(&response_bytes).await?;

        debug!("Response sent successfully");

        Ok(())
    }

    /// Load or initialize session key (exposed for testing).
    ///
    /// **Note:** This is public only for integration tests. Production code
    /// should use `Server::new()` which calls this internally.
    pub fn load_or_init_session_key_public(config: &Config) -> Result<(Vec<u8>, PathBuf)> {
        Self::load_or_init_session_key(config)
    }

    /// Compute HMAC authentication for a request.
    ///
    /// Used for testing to generate valid auth values.
    pub fn compute_request_auth(&self, request: &Request) -> Vec<u8> {
        use ring::hmac;

        let canonical_bytes = request.canonical_bytes_without_auth();
        let key = hmac::Key::new(hmac::HMAC_SHA256, &self.session_key);
        let tag = hmac::sign(&key, &canonical_bytes);
        tag.as_ref().to_vec()
    }

    /// Check if frame is registered (exposed for testing).
    pub fn is_frame_registered(&self, frame_id: Uuid) -> bool {
        self.frames.contains(frame_id)
    }

    /// Handle a single request and return response.
    ///
    /// Validates HMAC authentication, then dispatches to appropriate handler.
    pub async fn handle_request(&self, request: Request) -> Result<Response> {
        // Validate HMAC
        if !self.validate_request_auth(&request)? {
            return Ok(Response::Error {
                error: "Authentication failed".to_string(),
                reason: "Invalid HMAC signature".to_string(),
            });
        }

        // Dispatch to handlers
        match request {
            Request::AuthorizeConstruct { frame_id, level, data_digest, .. } => {
                self.handle_authorize_construct(frame_id, level, data_digest).await
            }
            Request::RedeemGrant { grant_id, .. } => {
                self.handle_redeem_grant(grant_id).await
            }
            Request::ComputeSeal { frame_id, level, data_digest, .. } => {
                self.handle_compute_seal(frame_id, level, data_digest)
            }
            Request::VerifySeal { frame_id, level, data_digest, seal, .. } => {
                self.handle_verify_seal(frame_id, level, data_digest, seal)
            }
            Request::ConsumeConstructionTicket { .. } => {
                // Not implemented in Phase 2
                Ok(Response::Error {
                    error: "Not implemented".to_string(),
                    reason: "ConsumeConstructionTicket will be implemented in Phase 3".to_string(),
                })
            }
        }
    }

    /// Validate request HMAC authentication.
    fn validate_request_auth(&self, request: &Request) -> Result<bool> {
        use ring::hmac;

        let provided_auth = request.auth();
        let canonical_bytes = request.canonical_bytes_without_auth();

        let key = hmac::Key::new(hmac::HMAC_SHA256, &self.session_key);
        let expected_tag = hmac::sign(&key, &canonical_bytes);

        // Constant-time comparison
        Ok(provided_auth.len() == expected_tag.as_ref().len()
            && provided_auth == expected_tag.as_ref())
    }

    /// Handle AuthorizeConstruct request.
    async fn handle_authorize_construct(
        &self,
        frame_id: [u8; 16],
        level: u32,
        data_digest: [u8; 32],
    ) -> Result<Response> {
        use std::time::{SystemTime, UNIX_EPOCH};
        use crate::grants::GrantRequest;

        // Create grant request
        let request = GrantRequest {
            frame_id: Uuid::from_bytes(frame_id),
            level,
            data_digest,
        };

        // Authorize construction
        let grant_id = self.grants.authorize(request).await;

        // Calculate expiration time
        let now = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs_f64();
        let ttl_secs = self.config.grant_ttl().as_secs_f64();
        let expires_at = now + ttl_secs;

        Ok(Response::AuthorizeConstructReply {
            grant_id,
            expires_at,
        })
    }

    /// Handle RedeemGrant request.
    async fn handle_redeem_grant(&self, grant_id: [u8; 16]) -> Result<Response> {
        // Redeem grant (consumes one-shot handle)
        let grant_request = self.grants.redeem(&grant_id).await
            .map_err(|e| anyhow::anyhow!("Grant redemption failed: {}", e))?;

        // Register frame for future seal operations
        self.frames.register_from_grant(grant_request.clone());

        // Compute initial seal
        let uuid_frame_id = grant_request.frame_id;
        let seal = self.secrets.compute_seal(uuid_frame_id, grant_request.level, &grant_request.data_digest);

        // Return construction ticket (for Phase 3)
        Ok(Response::RedeemGrantReply {
            construction_ticket: self.secrets.construction_ticket(),
            seal,
            audit_id: 0, // TODO: Implement audit logging in Phase 3
        })
    }

    /// Handle ComputeSeal request.
    fn handle_compute_seal(
        &self,
        frame_id: [u8; 16],
        level: u32,
        data_digest: [u8; 32],
    ) -> Result<Response> {
        let uuid_frame_id = Uuid::from_bytes(frame_id);

        // Security check: frame must be registered
        if !self.frames.contains(uuid_frame_id) {
            return Ok(Response::Error {
                error: "Frame not registered".to_string(),
                reason: format!("Frame {} must be registered via grant redemption first", uuid_frame_id),
            });
        }

        // Compute seal
        let seal = self.secrets.compute_seal(uuid_frame_id, level, &data_digest);

        // Update frame metadata
        self.frames.update(uuid_frame_id, level, &data_digest)?;

        Ok(Response::ComputeSealReply {
            seal,
            audit_id: 0, // TODO: Implement audit logging in Phase 3
        })
    }

    /// Handle VerifySeal request.
    fn handle_verify_seal(
        &self,
        frame_id: [u8; 16],
        level: u32,
        data_digest: [u8; 32],
        seal: [u8; 32],
    ) -> Result<Response> {
        let uuid_frame_id = Uuid::from_bytes(frame_id);

        // Security check: frame must be registered
        if !self.frames.contains(uuid_frame_id) {
            return Ok(Response::Error {
                error: "Frame not registered".to_string(),
                reason: format!("Frame {} must be registered via grant redemption first", uuid_frame_id),
            });
        }

        // Verify seal
        let valid = self.secrets.verify_seal(uuid_frame_id, level, &data_digest, &seal);

        Ok(Response::VerifySealReply {
            valid,
            audit_id: 0, // TODO: Implement audit logging in Phase 3
        })
    }

    fn load_or_init_session_key(config: &Config) -> Result<(Vec<u8>, PathBuf)> {
        use ring::rand::{SecureRandom, SystemRandom};
        use std::fs::{File, OpenOptions};
        use std::io::{Read, Write};
        use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};

        let session_key_path = &config.session_key_path;

        // If file exists, reload existing key
        if session_key_path.exists() {
            debug!("Loading existing session key from {:?}", session_key_path);

            let mut file = File::open(session_key_path)
                .with_context(|| format!("Failed to open session key file: {:?}", session_key_path))?;

            let mut session_key = Vec::new();
            file.read_to_end(&mut session_key)
                .with_context(|| format!("Failed to read session key from {:?}", session_key_path))?;

            if session_key.len() != 32 {
                anyhow::bail!(
                    "Invalid session key length: {} bytes (expected 32)",
                    session_key.len()
                );
            }

            info!("Session key loaded from {:?} (32 bytes)", session_key_path);
            return Ok((session_key, session_key_path.clone()));
        }

        // Generate new session key
        info!("Generating new session key at {:?}", session_key_path);

        let rng = SystemRandom::new();
        let mut session_key = vec![0u8; 32];
        rng.fill(&mut session_key)
            .map_err(|_| anyhow::anyhow!("Failed to generate random session key"))?;

        // Create parent directory if needed
        if let Some(parent) = session_key_path.parent() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("Failed to create parent directory: {:?}", parent))?;
        }

        // Write key with 0o640 permissions (owner read/write, group read)
        let mut file = OpenOptions::new()
            .create_new(true) // O_CREAT | O_EXCL
            .write(true)
            .mode(0o640)
            .open(session_key_path)
            .with_context(|| {
                format!(
                    "Failed to create session key file: {:?} (ensure parent directory exists and is writable)",
                    session_key_path
                )
            })?;

        file.write_all(&session_key)
            .context("Failed to write session key")?;

        // fsync file
        file.sync_all()
            .context("Failed to fsync session key file")?;

        drop(file);

        // fsync parent directory (ensure directory entry is persisted)
        if let Some(parent) = session_key_path.parent() {
            let parent_dir = File::open(parent)
                .with_context(|| format!("Failed to open parent directory for fsync: {:?}", parent))?;
            parent_dir.sync_all()
                .with_context(|| format!("Failed to fsync parent directory: {:?}", parent))?;
        }

        // Verify permissions
        let metadata = std::fs::metadata(session_key_path)
            .context("Failed to read metadata after creation")?;
        let permissions = metadata.permissions();
        let mode = permissions.mode();

        if (mode & 0o777) != 0o640 {
            anyhow::bail!(
                "Session key file has incorrect permissions: {:o} (expected 0o640)",
                mode & 0o777
            );
        }

        info!("Session key generated and persisted at {:?} (32 bytes, mode 0o640)", session_key_path);

        Ok((session_key, session_key_path.clone()))
    }
}
