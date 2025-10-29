//! Configuration loading from TOML.

use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use std::time::Duration;

/// Sidecar daemon configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    /// Security mode: "sidecar" (hardened, production) or "standalone" (dev-only, OFFICIAL:SENSITIVE cap)
    /// REQUIRED: No default, must be explicitly set
    pub mode: SecurityMode,

    /// Unix socket path (e.g., /run/sidecar/auth.sock)
    pub socket_path: PathBuf,

    /// Session key file path (e.g., /run/sidecar/.session)
    pub session_key_path: PathBuf,

    /// UID of orchestrator process (for SO_PEERCRED check)
    pub appuser_uid: u32,

    /// Grant TTL in seconds
    pub grant_ttl_secs: u64,

    /// Log level (trace, debug, info, warn, error)
    pub log_level: String,
}

/// Security mode (explicit opt-in, no default)
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum SecurityMode {
    /// Hardened sidecar mode (production)
    /// - Secrets in Rust memory
    /// - UID separation enforced
    /// - SO_PEERCRED validation
    /// - Plugin worker isolation
    Sidecar,

    /// Standalone mode (development only)
    /// - OFFICIAL:SENSITIVE classification ceiling
    /// - Loud warning logs on every operation
    /// - Secrets remain in Python (CVE-ADR-002-A-009 UNFIXED)
    /// - NOT APPROVED for SECRET data
    Standalone,
}

impl Config {
    /// Load config from TOML file.
    pub fn load(path: &str) -> Result<Self> {
        let contents = fs::read_to_string(path)
            .with_context(|| format!("Failed to read config from {}", path))?;

        let config: Config = toml::from_str(&contents)
            .with_context(|| format!("Failed to parse TOML from {}", path))?;

        // SECURITY: Validate mode is explicitly set
        config.validate()?;

        Ok(config)
    }

    /// Validate configuration (fail-fast on missing/invalid settings).
    fn validate(&self) -> Result<()> {
        // Mode validation (explicit opt-in required)
        // NOTE: Serde will fail if mode is missing, but we document it here

        // Standalone mode validation
        if self.mode == SecurityMode::Standalone {
            tracing::warn!(
                "⚠️  STANDALONE MODE ACTIVE - CVE-ADR-002-A-009 UNFIXED ⚠️\n\
                 Classification ceiling: OFFICIAL:SENSITIVE\n\
                 Secrets remain in Python memory (vulnerable to introspection)\n\
                 NOT APPROVED for SECRET data\n\
                 See docs/architecture/decisions/002-security-architecture.md"
            );
        }

        Ok(())
    }

    /// Grant TTL as Duration.
    pub fn grant_ttl(&self) -> Duration {
        Duration::from_secs(self.grant_ttl_secs)
    }
}

// NO Default implementation - mode must be explicitly specified
// Attempting Config::default() will fail at compile time
