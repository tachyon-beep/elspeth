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

    fn load_or_init_session_key(_config: &Config) -> Result<(Vec<u8>, PathBuf)> {
        // TODO: Implement in Task 2.3 (secure session key generation + persistence)
        // For now, return placeholder key for compilation
        Ok((vec![0u8; 32], PathBuf::from("/tmp/placeholder.session")))
    }
}
