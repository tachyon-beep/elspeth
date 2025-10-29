use elspeth_sidecar::crypto::Secrets;
use uuid::Uuid;

fn fixed_digest(tag: u8) -> [u8; 32] {
    [tag; 32]
}

#[test]
fn test_secrets_generate_creates_random_values() {
    let frame_id = Uuid::new_v4();
    let digest = fixed_digest(0xAB);
    let seal1 = Secrets::generate().compute_seal(frame_id, 3, &digest);
    let seal2 = Secrets::generate().compute_seal(frame_id, 3, &digest);

    // Independent secrets should produce different seals with overwhelming probability.
    assert_ne!(seal1, seal2);
    assert_eq!(seal1.len(), 32);
    assert_eq!(seal2.len(), 32);
}

#[test]
fn test_secrets_compute_seal_deterministic() {
    let secrets = Secrets::generate();
    let frame_id = Uuid::new_v4();
    let digest = fixed_digest(0xAB);
    let level = 3u32; // SECRET

    let seal1 = secrets.compute_seal(frame_id, level, &digest);
    let seal2 = secrets.compute_seal(frame_id, level, &digest);

    // Same inputs produce same seal
    assert_eq!(seal1, seal2);
    assert_eq!(seal1.len(), 32);
}

#[test]
fn test_secrets_verify_seal_success() {
    let secrets = Secrets::generate();
    let frame_id = Uuid::new_v4();
    let digest = fixed_digest(0x42);

    let seal = secrets.compute_seal(frame_id, 2, &digest);

    // Verification succeeds for matching tuple
    assert!(secrets.verify_seal(frame_id, 2, &digest, &seal));
}

#[test]
fn test_secrets_verify_seal_fails_wrong_frame_id() {
    let secrets = Secrets::generate();
    let frame_id = Uuid::new_v4();
    let other_frame_id = Uuid::new_v4();
    let digest = fixed_digest(0x11);

    let seal = secrets.compute_seal(frame_id, 1, &digest);

    assert!(!secrets.verify_seal(other_frame_id, 1, &digest, &seal));
}

#[test]
fn test_secrets_verify_seal_fails_wrong_level() {
    let secrets = Secrets::generate();
    let frame_id = Uuid::new_v4();
    let digest = fixed_digest(0x22);

    let seal = secrets.compute_seal(frame_id, 4, &digest);

    assert!(!secrets.verify_seal(frame_id, 3, &digest, &seal));
}

#[test]
fn test_secrets_verify_seal_fails_wrong_digest() {
    let secrets = Secrets::generate();
    let frame_id = Uuid::new_v4();

    let seal = secrets.compute_seal(frame_id, 3, &fixed_digest(0x33));

    assert!(!secrets.verify_seal(frame_id, 3, &fixed_digest(0x34), &seal));
}
