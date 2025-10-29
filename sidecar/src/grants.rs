//! Grant table for one-shot authorization handles.
//!
//! - `authorize()`: Creates grant with TTL, returns 128-bit handle
//! - `redeem()`: Validates and consumes grant (one-shot)
//! - `cleanup_expired()`: Background task removes expired grants

use dashmap::DashMap;
use ring::rand::{SecureRandom, SystemRandom};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::{Duration, Instant};
use uuid::Uuid;

/// Request to authorize SecureDataFrame construction.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct GrantRequest {
    pub frame_id: Uuid,
    pub level: u32,
    pub data_digest: [u8; 32],
}

/// Grant state (stored in table until redeemed or expired).
#[derive(Clone, Debug)]
struct Grant {
    request: GrantRequest,
    expires_at: Instant,
}

/// Grant table with TTL-based expiry and one-shot redemption.
pub struct GrantTable {
    grants: Arc<DashMap<[u8; 16], Grant>>,
    ttl: Duration,
    rng: SystemRandom,
}

impl GrantTable {
    /// Create new grant table with specified TTL.
    pub fn new(ttl: Duration) -> Self {
        Self {
            grants: Arc::new(DashMap::new()),
            ttl,
            rng: SystemRandom::new(),
        }
    }

    /// Authorize construction, return 128-bit grant ID.
    pub async fn authorize(&self, request: GrantRequest) -> [u8; 16] {
        let mut grant_id = [0u8; 16];
        self.rng.fill(&mut grant_id).expect("RNG failure");

        let grant = Grant {
            request,
            expires_at: Instant::now() + self.ttl,
        };

        self.grants.insert(grant_id, grant);
        grant_id
    }

    /// Redeem grant (one-shot, removes from table).
    pub async fn redeem(&self, grant_id: &[u8; 16]) -> Result<GrantRequest, String> {
        let (_, grant) = self
            .grants
            .remove(grant_id)
            .ok_or_else(|| "Grant not found or already redeemed".to_string())?;

        if Instant::now() > grant.expires_at {
            return Err("Grant expired".to_string());
        }

        Ok(grant.request)
    }

    /// Remove expired grants (background cleanup task).
    pub async fn cleanup_expired(&self) {
        let now = Instant::now();
        self.grants.retain(|_, grant| grant.expires_at > now);
    }

    /// Count active grants (for testing).
    pub async fn active_count(&self) -> usize {
        self.grants.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[tokio::test]
    async fn test_authorize_creates_unique_ids() {
        let table = GrantTable::new(Duration::from_secs(60));
        let request = GrantRequest {
            frame_id: Uuid::new_v4(),
            level: 3,
            data_digest: [0xAA; 32],
        };

        let id1 = table.authorize(request.clone()).await;
        let id2 = table.authorize(request.clone()).await;

        assert_ne!(id1, id2);
    }
}
