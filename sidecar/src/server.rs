//! Unix socket server for daemon ↔ orchestrator IPC.

use crate::config::Config;
use crate::crypto::Secrets;
use crate::grants::GrantTable;
use crate::protocol::{Request, Response};
use anyhow::{Context, Result};
use std::path::PathBuf;
use std::sync::Arc;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{UnixListener, UnixStream};
use tracing::{debug, error, info};

/// Sidecar daemon server.
pub struct Server {
    config: Arc<Config>,
    secrets: Arc<Secrets>,
    grants: Arc<GrantTable>,
    session_key: Vec<u8>,
}

impl Server {
    /// Create new server with generated secrets.
    pub fn new(config: Config) -> Result<Self> {
        let secrets = Arc::new(Secrets::generate());
        let grants = Arc::new(GrantTable::new(config.grant_ttl()));
        let (_session_key, _session_key_path) = Self::load_or_init_session_key(&config)?;

        Ok(Self {
            config: Arc::new(config),
            secrets,
            grants,
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
                    let config = self.config.clone();
                    let secrets = self.secrets.clone();
                    let grants = self.grants.clone();
                    let session_key = self.session_key.clone();

                    tokio::spawn(async move {
                        if let Err(e) = Self::handle_client(stream, config, secrets, grants, session_key).await {
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
    async fn handle_client(
        mut stream: UnixStream,
        _config: Arc<Config>,
        _secrets: Arc<Secrets>,
        _grants: Arc<GrantTable>,
        _session_key: Vec<u8>,
    ) -> Result<()> {
        // TODO: SO_PEERCRED check

        debug!("Client connected");

        // Read CBOR frames
        let mut buffer = vec![0u8; 4096];
        let n = stream.read(&mut buffer).await?;

        if n == 0 {
            return Ok(()); // EOF
        }

        let request: Request = serde_cbor::from_slice(&buffer[..n])
            .context("Failed to parse CBOR request")?;

        debug!("Received request: {:?}", request);

        // TODO: Validate HMAC using session_key
        // TODO: Dispatch request
        // TODO: Send response

        let response = Response::Error {
            error: "Not implemented".to_string(),
            reason: "Server skeleton only".to_string(),
        };

        let response_bytes = serde_cbor::to_vec(&response)?;
        stream.write_all(&response_bytes).await?;

        Ok(())
    }

    /// Load or initialize session key (exposed for testing).
    ///
    /// **Note:** This is public only for integration tests. Production code
    /// should use `Server::new()` which calls this internally.
    pub fn load_or_init_session_key_public(config: &Config) -> Result<(Vec<u8>, PathBuf)> {
        Self::load_or_init_session_key(config)
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
