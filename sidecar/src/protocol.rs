//! CBOR protocol messages for daemon ↔ orchestrator communication.
//!
//! All messages include `auth` field with HMAC-BLAKE2s(session_key, canonical_cbor(request_without_auth)).

use serde::{Deserialize, Serialize};

/// Client request to daemon.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "op")]
pub enum Request {
    /// Request one-shot grant for `(frame_id, level, data_digest)`.
    #[serde(rename = "authorize_construct")]
    AuthorizeConstruct {
        #[serde(with = "serde_bytes")]
        frame_id: [u8; 16],  // UUID v4 serialized to 16 bytes (Uuid::as_bytes())
        level: u32,
        #[serde(with = "serde_bytes")]
        data_digest: [u8; 32],
        #[serde(with = "serde_bytes")]
        auth: Vec<u8>, // HMAC over canonical tuple
    },

    /// Redeem grant for seal.
    #[serde(rename = "redeem_grant")]
    RedeemGrant {
        #[serde(with = "serde_bytes")]
        grant_id: [u8; 16],
        #[serde(with = "serde_bytes")]
        auth: Vec<u8>, // HMAC of grant_id
    },

    /// Consume construction ticket before instantiation.
    #[serde(rename = "consume_construction_ticket")]
    ConsumeConstructionTicket {
        #[serde(with = "serde_bytes")]
        ticket: [u8; 32],
        #[serde(with = "serde_bytes")]
        auth: Vec<u8>,
    },

    /// Compute seal for existing frame.
    #[serde(rename = "compute_seal")]
    ComputeSeal {
        #[serde(with = "serde_bytes")]
        frame_id: [u8; 16],
        level: u32,
        #[serde(with = "serde_bytes")]
        data_digest: [u8; 32],
        #[serde(with = "serde_bytes")]
        auth: Vec<u8>,
    },

    /// Verify seal integrity.
    #[serde(rename = "verify_seal")]
    VerifySeal {
        #[serde(with = "serde_bytes")]
        frame_id: [u8; 16],
        level: u32,
        #[serde(with = "serde_bytes")]
        data_digest: [u8; 32],
        #[serde(with = "serde_bytes")]
        seal: [u8; 32],
        #[serde(with = "serde_bytes")]
        auth: Vec<u8>,
    },
}

/// Daemon response to client.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Response {
    /// Grant authorized (expires after TTL).
    AuthorizeConstructReply {
        #[serde(with = "serde_bytes")]
        grant_id: [u8; 16],
        expires_at: f64, // Unix timestamp
    },

    /// Grant redeemed, seal computed.
    RedeemGrantReply {
        #[serde(with = "serde_bytes")]
        construction_ticket: [u8; 32],
        #[serde(with = "serde_bytes")]
        seal: [u8; 32],
        audit_id: u64,
    },

    /// Seal computed.
    ComputeSealReply {
        #[serde(with = "serde_bytes")]
        seal: [u8; 32],
        audit_id: u64,
    },

    /// Ticket consumption acknowledgement.
    ConsumeTicketReply {
        consumed: bool,
        audit_id: u64,
    },

    /// Seal verification result.
    VerifySealReply {
        valid: bool,
        audit_id: u64,
    },

    /// Error response.
    Error {
        error: String,
        reason: String,
    },
}

impl Request {
    /// Extract auth field for validation.
    pub fn auth(&self) -> &[u8] {
        match self {
            Request::AuthorizeConstruct { auth, .. } => auth,
            Request::RedeemGrant { auth, .. } => auth,
            Request::ConsumeConstructionTicket { auth, .. } => auth,
            Request::ComputeSeal { auth, .. } => auth,
            Request::VerifySeal { auth, .. } => auth,
        }
    }

    /// Canonical CBOR bytes (without auth field) for HMAC computation.
    pub fn canonical_bytes_without_auth(&self) -> Vec<u8> {
        match self {
            Request::AuthorizeConstruct {
                frame_id,
                level,
                data_digest,
                ..
            } => serde_cbor::to_vec(&(
                serde_bytes::Bytes::new(frame_id),
                *level,
                serde_bytes::Bytes::new(data_digest),
            )).unwrap(),
            Request::RedeemGrant { grant_id, .. } => {
                serde_cbor::to_vec(&serde_bytes::Bytes::new(grant_id)).unwrap()
            }
            Request::ConsumeConstructionTicket { ticket, .. } => {
                serde_cbor::to_vec(&serde_bytes::Bytes::new(ticket)).unwrap()
            }
            Request::ComputeSeal {
                frame_id,
                level,
                data_digest,
                ..
            } => serde_cbor::to_vec(&(
                serde_bytes::Bytes::new(frame_id),
                *level,
                serde_bytes::Bytes::new(data_digest),
            )).unwrap(),
            Request::VerifySeal {
                frame_id,
                level,
                data_digest,
                seal,
                ..
            } => serde_cbor::to_vec(&(
                serde_bytes::Bytes::new(frame_id),
                *level,
                serde_bytes::Bytes::new(data_digest),
                serde_bytes::Bytes::new(seal),
            )).unwrap(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_canonical_bytes_deterministic() {
        let req = Request::AuthorizeConstruct {
            frame_id: [0x01; 16],
            level: 3,
            data_digest: [0x02; 32],
            auth: vec![],
        };

        let bytes1 = req.canonical_bytes_without_auth();
        let bytes2 = req.canonical_bytes_without_auth();

        assert_eq!(bytes1, bytes2);
    }
}
