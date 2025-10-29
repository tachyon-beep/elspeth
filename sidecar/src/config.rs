//! Configuration loading for sidecar daemon

use anyhow::Result;
use serde::{Deserialize, Serialize};

/// Security mode (explicit opt-in, no default)
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum SecurityMode {
    /// Hardened sidecar mode (production)
    Sidecar,
    /// Standalone mode (development only)
    Standalone,
}

/// Daemon configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub mode: SecurityMode,
    pub socket_path: String,
    pub session_key_path: String,
}

impl Config {
    /// Load config from TOML file (placeholder)
    pub fn load(_path: &str) -> Result<Self> {
        // TODO: Implement in Task 1.5
        unimplemented!("Config loading not yet implemented")
    }
}
