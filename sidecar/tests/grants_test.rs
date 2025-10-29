use elspeth_sidecar::grants::{GrantRequest, GrantTable};
use std::time::Duration;
use uuid::Uuid;

fn digest(tag: u8) -> [u8; 32] {
    [tag; 32]
}

#[tokio::test]
async fn test_grant_authorize_and_redeem_success() {
    let table = GrantTable::new(Duration::from_secs(60));
    let request = GrantRequest {
        frame_id: Uuid::new_v4(),
        level: 3,
        data_digest: digest(0x90),
    };

    // Authorize creates grant
    let grant_id = table.authorize(request.clone()).await;
    assert_eq!(grant_id.len(), 16);

    // Redeem succeeds once
    let result = table.redeem(&grant_id).await;
    assert!(result.is_ok());
    let redeemed = result.unwrap();
    assert_eq!(redeemed.frame_id, request.frame_id);
    assert_eq!(redeemed.level, 3);
    assert_eq!(redeemed.data_digest, request.data_digest);

    // Redeem fails second time (one-shot)
    let result2 = table.redeem(&grant_id).await;
    assert!(result2.is_err());
}

#[tokio::test]
async fn test_grant_expires_after_ttl() {
    let table = GrantTable::new(Duration::from_millis(100));
    let request = GrantRequest {
        frame_id: Uuid::new_v4(),
        level: 3,
        data_digest: digest(0x33),
    };

    let grant_id = table.authorize(request).await;

    // Wait for expiry
    tokio::time::sleep(Duration::from_millis(150)).await;

    // Redeem fails (expired)
    let result = table.redeem(&grant_id).await;
    assert!(matches!(result, Err(_)));
}

#[tokio::test]
async fn test_grant_cleanup_removes_expired() {
    let table = GrantTable::new(Duration::from_millis(50));

    // Create 3 grants
    for tag in 0..3 {
        let request = GrantRequest {
            frame_id: Uuid::new_v4(),
            level: 3,
            data_digest: digest(tag),
        };
        table.authorize(request).await;
    }

    // Wait for expiry
    tokio::time::sleep(Duration::from_millis(100)).await;

    // Trigger cleanup
    table.cleanup_expired().await;

    // All grants should be removed (checking via active count)
    assert_eq!(table.active_count().await, 0);
}
