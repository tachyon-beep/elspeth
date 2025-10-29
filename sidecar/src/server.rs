//! Unix socket server for daemon ↔ orchestrator IPC.

use crate::config::Config;
use crate::crypto::Secrets;
use crate::frames::RegisteredFrameTable;
use crate::grants::{ConstructionTicketTable, GrantTable};
use crate::protocol::{Request, Response};
use anyhow::{Context, Result};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Instant;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{UnixListener, UnixStream};
use tracing::{debug, error, info};
use uuid::Uuid;

/// Sidecar daemon server.
pub struct Server {
    config: Arc<Config>,
    secrets: Arc<Secrets>,
    grants: Arc<GrantTable>,
    tickets: Arc<ConstructionTicketTable>,
    frames: Arc<RegisteredFrameTable>,
    session_key: Vec<u8>,
    start_time: Instant,
    requests_served: Arc<AtomicU64>,
}

impl Server {
    /// Create new server with generated secrets.
    pub fn new(config: Config) -> Result<Self> {
        let secrets = Arc::new(Secrets::generate());
        let grants = Arc::new(GrantTable::new(config.grant_ttl()));
        let tickets = Arc::new(ConstructionTicketTable::new(config.grant_ttl()));
        let frames = Arc::new(RegisteredFrameTable::new());
        let (_session_key, _session_key_path) = Self::load_or_init_session_key(&config)?;

        Ok(Self {
            config: Arc::new(config),
            secrets,
            grants,
            tickets,
            frames,
            session_key: _session_key,
            start_time: Instant::now(),
            requests_served: Arc::new(AtomicU64::new(0)),
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
        let listener =
            UnixListener::bind(&self.config.socket_path).context("Failed to bind Unix socket")?;

        // Set socket permissions to 0600 (owner-only read/write)
        // This prevents unauthorized access even before SO_PEERCRED check
        use std::os::unix::fs::PermissionsExt;
        let mut perms = std::fs::metadata(&self.config.socket_path)?.permissions();
        perms.set_mode(0o600);
        std::fs::set_permissions(&self.config.socket_path, perms)
            .context("Failed to set socket permissions to 0600")?;

        info!("Listening on {:?} (mode 0600)", self.config.socket_path);

        // Accept connections
        loop {
            match listener.accept().await {
                Ok((stream, _addr)) => {
                    // Clone server state for spawn
                    let server = Server {
                        config: self.config.clone(),
                        secrets: self.secrets.clone(),
                        grants: self.grants.clone(),
                        tickets: self.tickets.clone(),
                        frames: self.frames.clone(),
                        session_key: self.session_key.clone(),
                        start_time: self.start_time,
                        requests_served: self.requests_served.clone(),
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
        // SO_PEERCRED check: Verify client UID matches expected appuser_uid
        let peer_uid = Self::get_peer_uid(&stream)?;
        let expected_uid = self.config.appuser_uid;

        if peer_uid != expected_uid {
            error!(
                "SO_PEERCRED check failed: client UID {} != expected {} (appuser)",
                peer_uid, expected_uid
            );
            anyhow::bail!(
                "Authentication failed: client must run as UID {} (appuser), got UID {}",
                expected_uid,
                peer_uid
            );
        }

        debug!("Client connected (UID {} verified)", peer_uid);

        // Read complete CBOR request (read until EOF)
        // Unix sockets are stream-oriented - must read until connection closes
        let mut buffer = Vec::new();
        stream.read_to_end(&mut buffer).await?;

        if buffer.is_empty() {
            return Ok(()); // EOF
        }

        debug!(
            "Received {} bytes: {:?}",
            buffer.len(),
            &buffer[..buffer.len().min(128)]
        );

        let request: Request = serde_cbor::from_slice(&buffer)
            .map_err(|e| {
                error!("CBOR parse error: {:?}", e);
                error!("Received bytes (full): {:?}", &buffer);
                e
            })
            .context("Failed to parse CBOR request")?;

        debug!("Received request: {:?}", request);

        // Dispatch request (includes HMAC validation)
        // Convert any errors to Error responses instead of closing connection
        let response = match self.handle_request(request).await {
            Ok(resp) => resp,
            Err(e) => {
                error!("Request handling error: {:#}", e);
                Response::Error {
                    error: "Request failed".to_string(),
                    reason: format!("{:#}", e),
                }
            }
        };

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
        // Skip HMAC validation for health checks
        if request.requires_auth() && !self.validate_request_auth(&request)? {
            return Ok(Response::Error {
                error: "Authentication failed".to_string(),
                reason: "Invalid HMAC signature".to_string(),
            });
        }

        // Increment request counter
        self.requests_served.fetch_add(1, Ordering::Relaxed);

        // Dispatch to handlers
        match request {
            Request::AuthorizeConstruct {
                frame_id,
                level,
                data_digest,
                ..
            } => {
                self.handle_authorize_construct(frame_id, level, data_digest)
                    .await
            }
            Request::RedeemGrant { grant_id, .. } => self.handle_redeem_grant(grant_id).await,
            Request::ComputeSeal {
                frame_id,
                level,
                data_digest,
                ..
            } => self.handle_compute_seal(frame_id, level, data_digest),
            Request::VerifySeal {
                frame_id,
                level,
                data_digest,
                seal,
                ..
            } => self.handle_verify_seal(frame_id, level, data_digest, seal),
            Request::HealthCheck => Ok(self.handle_health_check()),
            Request::ConsumeConstructionTicket { ticket, .. } => {
                self.handle_consume_construction_ticket(ticket).await
            }
        }
    }

    /// Validate request HMAC authentication.
    fn validate_request_auth(&self, request: &Request) -> Result<bool> {
        use ring::hmac;

        let provided_auth = match request.auth() {
            Some(auth) => auth,
            None => return Ok(true), // No auth required
        };

        let canonical_bytes = request.canonical_bytes_without_auth();

        let key = hmac::Key::new(hmac::HMAC_SHA256, &self.session_key);

        // Use ring::hmac::verify for constant-time comparison
        // This prevents timing side-channel attacks
        match hmac::verify(&key, &canonical_bytes, provided_auth) {
            Ok(()) => Ok(true),
            Err(_) => Ok(false),
        }
    }

    /// Handle health check request (no authentication required).
    fn handle_health_check(&self) -> Response {
        let uptime_secs = self.start_time.elapsed().as_secs();
        let requests_served = self.requests_served.load(Ordering::Relaxed);

        Response::HealthCheckReply {
            status: "healthy".to_string(),
            uptime_secs,
            requests_served,
        }
    }

    /// Handle AuthorizeConstruct request.
    async fn handle_authorize_construct(
        &self,
        frame_id: [u8; 16],
        level: u32,
        data_digest: [u8; 32],
    ) -> Result<Response> {
        use crate::grants::GrantRequest;
        use std::time::{SystemTime, UNIX_EPOCH};

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
        // Redeem grant (consumes one-shot handle, returns unique construction_ticket)
        let (grant_request, construction_ticket) = self
            .grants
            .redeem(&grant_id)
            .await
            .map_err(|e| anyhow::anyhow!("Grant redemption failed: {}", e))?;

        // SECURITY: Record ticket as issued (prevents forgery attacks)
        // Without this, any random 32-byte value would be accepted as a valid ticket
        self.tickets.issue(construction_ticket).await;

        // Register frame for future seal operations
        self.frames.register_from_grant(grant_request.clone());

        // Compute initial seal
        let uuid_frame_id = grant_request.frame_id;
        let seal = self.secrets.compute_seal(
            uuid_frame_id,
            grant_request.level,
            &grant_request.data_digest,
        );

        // Return unique construction ticket (one-shot, must be consumed before frame instantiation)
        Ok(Response::RedeemGrantReply {
            construction_ticket,
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
                reason: format!(
                    "Frame {} must be registered via grant redemption first",
                    uuid_frame_id
                ),
            });
        }

        // Compute seal
        let seal = self
            .secrets
            .compute_seal(uuid_frame_id, level, &data_digest);

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
                reason: format!(
                    "Frame {} must be registered via grant redemption first",
                    uuid_frame_id
                ),
            });
        }

        // Verify seal
        let valid = self
            .secrets
            .verify_seal(uuid_frame_id, level, &data_digest, &seal);

        Ok(Response::VerifySealReply {
            valid,
            audit_id: 0, // TODO: Implement audit logging in Phase 3
        })
    }

    /// Handle ConsumeConstructionTicket request.
    async fn handle_consume_construction_ticket(&self, ticket: [u8; 32]) -> Result<Response> {
        // Attempt to consume the ticket (one-shot)
        match self.tickets.consume(&ticket).await {
            Ok(()) => {
                Ok(Response::ConsumeTicketReply {
                    consumed: true,
                    audit_id: 0, // TODO: Implement audit logging in Phase 3
                })
            }
            Err(e) => Ok(Response::Error {
                error: "Ticket consumption failed".to_string(),
                reason: e,
            }),
        }
    }

    /// Get peer UID from Unix socket using SO_PEERCRED.
    ///
    /// **Platform**: Linux-only (uses SO_PEERCRED socket option).
    #[cfg(target_os = "linux")]
    fn get_peer_uid(stream: &UnixStream) -> Result<u32> {
        use std::os::unix::io::AsRawFd;

        // SO_PEERCRED structure from libc
        #[repr(C)]
        #[derive(Copy, Clone)]
        struct ucred {
            pid: libc::pid_t,
            uid: libc::uid_t,
            gid: libc::gid_t,
        }

        let mut ucred = ucred {
            pid: 0,
            uid: 0,
            gid: 0,
        };

        let mut len = std::mem::size_of::<ucred>() as libc::socklen_t;

        let ret = unsafe {
            libc::getsockopt(
                stream.as_raw_fd(),
                libc::SOL_SOCKET,
                libc::SO_PEERCRED,
                &mut ucred as *mut _ as *mut libc::c_void,
                &mut len,
            )
        };

        if ret != 0 {
            anyhow::bail!(
                "getsockopt(SO_PEERCRED) failed: {}",
                std::io::Error::last_os_error()
            );
        }

        Ok(ucred.uid)
    }

    /// Fallback for non-Linux platforms (compile error with helpful message).
    #[cfg(not(target_os = "linux"))]
    fn get_peer_uid(_stream: &UnixStream) -> Result<u32> {
        compile_error!("SO_PEERCRED is only supported on Linux. For other platforms, implement equivalent peer credential check.");
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

            let mut file = File::open(session_key_path).with_context(|| {
                format!("Failed to open session key file: {:?}", session_key_path)
            })?;

            let mut session_key = Vec::new();
            file.read_to_end(&mut session_key).with_context(|| {
                format!("Failed to read session key from {:?}", session_key_path)
            })?;

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
            let parent_dir = File::open(parent).with_context(|| {
                format!("Failed to open parent directory for fsync: {:?}", parent)
            })?;
            parent_dir
                .sync_all()
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

        info!(
            "Session key generated and persisted at {:?} (32 bytes, mode 0o640)",
            session_key_path
        );

        Ok((session_key, session_key_path.clone()))
    }
}
