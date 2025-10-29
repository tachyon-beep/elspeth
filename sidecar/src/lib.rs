//! Elspeth Sidecar Security Daemon
//!
//! OS-isolated process holding `_CONSTRUCTION_TOKEN` and `_SEAL_KEY` in Rust memory.
//! Provides capability-based authorization via Unix socket with HMAC authentication.

pub mod config;
pub mod crypto;
pub mod protocol;
pub mod server;
pub mod grants;
pub mod frames;

pub use config::Config;
pub use server::Server;
