use elspeth_sidecar::frames::RegisteredFrameTable;
use elspeth_sidecar::grants::GrantRequest;
use uuid::Uuid;

fn digest(tag: u8) -> [u8; 32] {
    [tag; 32]
}

#[test]
fn test_register_frame_makes_it_discoverable() {
    let table = RegisteredFrameTable::new();
    let frame_id = Uuid::new_v4();

    let request = GrantRequest {
        frame_id,
        level: 3,
        data_digest: digest(0xAA),
    };

    table.register_from_grant(request.clone());

    // Frame should now be discoverable
    assert!(table.contains(frame_id), "Frame should be registered");

    let metadata = table.get(frame_id);
    assert!(metadata.is_some(), "Metadata should be retrievable");

    let metadata = metadata.unwrap();
    assert_eq!(metadata.level, 3);
    assert_eq!(metadata.data_digest, digest(0xAA));
}

#[test]
fn test_update_unknown_frame_returns_error() {
    let table = RegisteredFrameTable::new();
    let unknown_frame_id = Uuid::new_v4();

    let result = table.update(unknown_frame_id, 2, &digest(0xBB));
    assert!(result.is_err(), "Updating unknown frame should fail");
}

#[test]
fn test_update_existing_frame_succeeds() {
    let table = RegisteredFrameTable::new();
    let frame_id = Uuid::new_v4();

    // Register initial frame
    let request = GrantRequest {
        frame_id,
        level: 3,
        data_digest: digest(0xAA),
    };
    table.register_from_grant(request);

    // Update with new level and digest
    let result = table.update(frame_id, 4, &digest(0xCC));
    assert!(result.is_ok(), "Updating known frame should succeed");

    // Verify metadata reflects latest values
    let metadata = table.get(frame_id).unwrap();
    assert_eq!(metadata.level, 4, "Level should be updated");
    assert_eq!(
        metadata.data_digest,
        digest(0xCC),
        "Digest should be updated"
    );
}

#[test]
fn test_contains_returns_false_for_unknown_frame() {
    let table = RegisteredFrameTable::new();
    let unknown_frame_id = Uuid::new_v4();

    assert!(
        !table.contains(unknown_frame_id),
        "Unknown frame should not be contained"
    );
}

#[test]
fn test_get_returns_none_for_unknown_frame() {
    let table = RegisteredFrameTable::new();
    let unknown_frame_id = Uuid::new_v4();

    let metadata = table.get(unknown_frame_id);
    assert!(metadata.is_none(), "Unknown frame should return None");
}

#[test]
fn test_multiple_frames_independent() {
    let table = RegisteredFrameTable::new();
    let frame1 = Uuid::new_v4();
    let frame2 = Uuid::new_v4();

    table.register_from_grant(GrantRequest {
        frame_id: frame1,
        level: 2,
        data_digest: digest(0x11),
    });

    table.register_from_grant(GrantRequest {
        frame_id: frame2,
        level: 4,
        data_digest: digest(0x22),
    });

    // Both frames should be independently retrievable
    let meta1 = table.get(frame1).unwrap();
    let meta2 = table.get(frame2).unwrap();

    assert_eq!(meta1.level, 2);
    assert_eq!(meta1.data_digest, digest(0x11));

    assert_eq!(meta2.level, 4);
    assert_eq!(meta2.data_digest, digest(0x22));
}
