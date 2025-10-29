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
    construction_ticket: [u8; 32],  // Unique random ticket issued with this grant
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

        // Generate unique construction ticket (32-byte random)
        let mut construction_ticket = [0u8; 32];
        self.rng.fill(&mut construction_ticket).expect("RNG failure");

        let grant = Grant {
            request,
            construction_ticket,
            expires_at: Instant::now() + self.ttl,
        };

        self.grants.insert(grant_id, grant);
        grant_id
    }

    /// Redeem grant (one-shot, removes from table).
    ///
    /// Returns both the GrantRequest and the construction_ticket.
    pub async fn redeem(&self, grant_id: &[u8; 16]) -> Result<(GrantRequest, [u8; 32]), String> {
        let (_, grant) = self
            .grants
            .remove(grant_id)
            .ok_or_else(|| "Grant not found or already redeemed".to_string())?;

        if Instant::now() > grant.expires_at {
            return Err("Grant expired".to_string());
        }

        Ok((grant.request, grant.construction_ticket))
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

/// Construction ticket table for one-shot ticket consumption validation.
///
/// Tracks which construction tickets have been consumed to prevent replay attacks.
pub struct ConstructionTicketTable {
    consumed_tickets: Arc<DashMap<[u8; 32], Instant>>,
    ttl: Duration,
}

impl ConstructionTicketTable {
    /// Create new ticket table with specified TTL.
    pub fn new(ttl: Duration) -> Self {
        Self {
            consumed_tickets: Arc::new(DashMap::new()),
            ttl,
        }
    }

    /// Consume a construction ticket (one-shot).
    ///
    /// Returns Ok(()) if ticket is valid and hasn't been consumed yet.
    /// Returns Err if ticket was already consumed or is invalid.
    pub async fn consume(&self, ticket: &[u8; 32]) -> Result<(), String> {
        // Check if ticket was already consumed
        if self.consumed_tickets.contains_key(ticket) {
            return Err("Construction ticket already consumed".to_string());
        }

        // Mark ticket as consumed with expiry time
        let expires_at = Instant::now() + self.ttl;
        self.consumed_tickets.insert(*ticket, expires_at);

        Ok(())
    }

    /// Remove expired consumed tickets (background cleanup task).
    pub async fn cleanup_expired(&self) {
        let now = Instant::now();
        self.consumed_tickets.retain(|_, &mut expires_at| expires_at > now);
    }

    /// Check if ticket was consumed (for testing).
    pub async fn is_consumed(&self, ticket: &[u8; 32]) -> bool {
        self.consumed_tickets.contains_key(ticket)
    }

    /// Count consumed tickets (for testing).
    pub async fn consumed_count(&self) -> usize {
        self.consumed_tickets.len()
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

    #[tokio::test]
    async fn test_ticket_consumption_is_one_shot() {
        let table = ConstructionTicketTable::new(Duration::from_secs(60));
        let ticket = [0xBB; 32];

        // First consumption succeeds
        assert!(table.consume(&ticket).await.is_ok());

        // Second consumption fails
        assert!(table.consume(&ticket).await.is_err());
    }

    #[tokio::test]
    async fn test_different_tickets_can_be_consumed() {
        let table = ConstructionTicketTable::new(Duration::from_secs(60));
        let ticket1 = [0xCC; 32];
        let ticket2 = [0xDD; 32];

        assert!(table.consume(&ticket1).await.is_ok());
        assert!(table.consume(&ticket2).await.is_ok());
    }
}
