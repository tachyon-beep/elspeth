//! Cryptographic primitives for sidecar daemon.
//!
//! - `Secrets`: Holds construction token and seal key in Rust memory
//! - `compute_seal()`: BLAKE2s-MAC(seal_key, frame_id || level || data_digest)
//! - `verify_seal()`: Constant-time seal comparison

use blake2::digest::{FixedOutput, KeyInit, Update};
use blake2::Blake2sMac256;
use ring::rand::{SecureRandom, SystemRandom};
use uuid::Uuid;

/// Secrets held in Rust memory (never exported to Python).
pub struct Secrets {
    construction_token: [u8; 32],
    seal_key: [u8; 32],
}

impl Secrets {
    /// Generate fresh secrets using cryptographically secure RNG.
    pub fn generate() -> Self {
        let rng = SystemRandom::new();

        // Generate construction token (256-bit random)
        let mut construction_token = [0u8; 32];
        rng.fill(&mut construction_token).expect("RNG failure");

        // Generate seal key (256-bit random for BLAKE2s MAC)
        let mut seal_key_bytes = [0u8; 32];
        rng.fill(&mut seal_key_bytes).expect("RNG failure");

        Self {
            construction_token,
            seal_key: seal_key_bytes,
        }
    }

    /// Return construction ticket (for grant redemption).
    pub fn construction_ticket(&self) -> [u8; 32] {
        self.construction_token
    }

    /// Compute tamper-evident seal for `(frame_id, level, data_digest)`.
    ///
    /// Seal = BLAKE2s-MAC(seal_key, frame_id || level || data_digest)
    pub fn compute_seal(&self, frame_id: Uuid, level: u32, data_digest: &[u8; 32]) -> [u8; 32] {
        let mut message = Vec::with_capacity(16 + 4 + 32);
        message.extend_from_slice(frame_id.as_bytes());
        message.extend_from_slice(&level.to_be_bytes());
        message.extend_from_slice(data_digest);

        let mut mac = Blake2sMac256::new_from_slice(&self.seal_key)
            .expect("seal key length must be 32 bytes");
        mac.update(&message);
        let output = mac.finalize_fixed();
        let mut seal = [0u8; 32];
        seal.copy_from_slice(&output);
        seal
    }

    /// Verify seal using constant-time comparison.
    pub fn verify_seal(
        &self,
        frame_id: Uuid,
        level: u32,
        data_digest: &[u8; 32],
        seal: &[u8],
    ) -> bool {
        use subtle::ConstantTimeEq;
        let expected = self.compute_seal(frame_id, level, data_digest);

        // Ensure same length for constant-time comparison
        if seal.len() != expected.len() {
            return false;
        }

        seal.ct_eq(&expected).into()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use uuid::Uuid;

    #[test]
    fn test_compute_seal_deterministic() {
        let secrets = Secrets::generate();
        let frame = Uuid::new_v4();
        let digest = [0x55; 32];
        let seal1 = secrets.compute_seal(frame, 3, &digest);
        let seal2 = secrets.compute_seal(frame, 3, &digest);
        assert_eq!(seal1, seal2);
    }

    #[test]
    fn test_verify_seal_success() {
        let secrets = Secrets::generate();
        let frame = Uuid::new_v4();
        let digest = [0x66; 32];
        let seal = secrets.compute_seal(frame, 3, &digest);
        assert!(secrets.verify_seal(frame, 3, &digest, &seal));
    }

    #[test]
    fn test_verify_seal_wrong_frame_id() {
        let secrets = Secrets::generate();
        let frame = Uuid::new_v4();
        let digest = [0x44; 32];
        let seal = secrets.compute_seal(frame, 3, &digest);
        assert!(!secrets.verify_seal(Uuid::new_v4(), 3, &digest, &seal));
    }
}
