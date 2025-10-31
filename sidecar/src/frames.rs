//! Registered frame table for tracking legitimate frame IDs.
//!
//! Prevents attackers from minting arbitrary frame identifiers and obtaining seals.
//! Only frames that were created via grant redemption are allowed to compute/verify seals.

use crate::grants::GrantRequest;
use anyhow::{bail, Result};
use dashmap::DashMap;
use uuid::Uuid;

/// Metadata for a registered frame.
#[derive(Debug, Clone)]
pub struct FrameMetadata {
    pub level: u32,
    pub data_digest: [u8; 32],
}

/// Table tracking registered frames (frames created via grant redemption).
pub struct RegisteredFrameTable {
    frames: DashMap<Uuid, FrameMetadata>,
}

impl RegisteredFrameTable {
    /// Create new empty frame table.
    pub fn new() -> Self {
        Self {
            frames: DashMap::new(),
        }
    }

    /// Register a frame from a redeemed grant.
    ///
    /// This is called immediately after `GrantTable::redeem()` succeeds.
    pub fn register_from_grant(&self, grant: GrantRequest) {
        let metadata = FrameMetadata {
            level: grant.level,
            data_digest: grant.data_digest,
        };

        self.frames.insert(grant.frame_id, metadata);
    }

    /// Update frame metadata (called after compute_seal).
    ///
    /// Returns error if frame is not registered.
    pub fn update(&self, frame_id: Uuid, level: u32, digest: &[u8; 32]) -> Result<()> {
        if !self.contains(frame_id) {
            bail!("Cannot update unknown frame: {}", frame_id);
        }

        let metadata = FrameMetadata {
            level,
            data_digest: *digest,
        };

        self.frames.insert(frame_id, metadata);
        Ok(())
    }

    /// Get frame metadata.
    pub fn get(&self, frame_id: Uuid) -> Option<FrameMetadata> {
        self.frames.get(&frame_id).map(|entry| entry.clone())
    }

    /// Check if frame is registered.
    pub fn contains(&self, frame_id: Uuid) -> bool {
        self.frames.contains_key(&frame_id)
    }
}

impl Default for RegisteredFrameTable {
    fn default() -> Self {
        Self::new()
    }
}
