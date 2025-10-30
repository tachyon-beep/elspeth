use elspeth_sidecar::protocol::{Request, Response};

fn digest(tag: u8) -> [u8; 32] {
    [tag; 32]
}

fn frame(tag: u8) -> [u8; 16] {
    [tag; 16]
}

#[test]
fn test_authorize_construct_request_serialization() {
    let request = Request::AuthorizeConstruct {
        frame_id: frame(0xAA),
        level: 3,
        data_digest: digest(0xBB),
        auth: vec![0xAB; 32],
    };

    // Serialize to CBOR
    let mut bytes = Vec::new(); ciborium::ser::into_writer(&request, &mut bytes).unwrap();

    // Deserialize back
    let decoded: Request = ciborium::de::from_reader(&bytes[..]).unwrap();

    match decoded {
        Request::AuthorizeConstruct {
            frame_id,
            level,
            data_digest,
            auth,
        } => {
            assert_eq!(frame_id, frame(0xAA));
            assert_eq!(level, 3);
            assert_eq!(data_digest, digest(0xBB));
            assert_eq!(auth, vec![0xAB; 32]);
        }
        _ => panic!("Wrong variant"),
    }
}

#[test]
fn test_authorize_construct_reply_serialization() {
    let response = Response::AuthorizeConstructReply {
        grant_id: [0xFF; 16],
        expires_at: 1698765432.123,
    };

    let mut bytes = Vec::new(); ciborium::ser::into_writer(&response, &mut bytes).unwrap();
    let decoded: Response = ciborium::de::from_reader(&bytes[..]).unwrap();

    match decoded {
        Response::AuthorizeConstructReply {
            grant_id,
            expires_at,
        } => {
            assert_eq!(grant_id, [0xFF; 16]);
            assert_eq!(expires_at, 1698765432.123);
        }
        _ => panic!("Wrong variant"),
    }
}

#[test]
fn test_error_response_serialization() {
    let response = Response::Error {
        error: "Grant not found".to_string(),
        reason: "Already redeemed".to_string(),
    };

    let mut bytes = Vec::new(); ciborium::ser::into_writer(&response, &mut bytes).unwrap();
    let decoded: Response = ciborium::de::from_reader(&bytes[..]).unwrap();

    match decoded {
        Response::Error { error, reason } => {
            assert_eq!(error, "Grant not found");
            assert_eq!(reason, "Already redeemed");
        }
        _ => panic!("Wrong variant"),
    }
}

#[test]
fn test_redeem_grant_round_trip() {
    let request = Request::RedeemGrant {
        grant_id: [0xCC; 16],
        auth: vec![0xDD; 32],
    };

    let mut bytes = Vec::new(); ciborium::ser::into_writer(&request, &mut bytes).unwrap();
    let decoded: Request = ciborium::de::from_reader(&bytes[..]).unwrap();

    match decoded {
        Request::RedeemGrant { grant_id, auth } => {
            assert_eq!(grant_id, [0xCC; 16]);
            assert_eq!(auth, vec![0xDD; 32]);
        }
        _ => panic!("Wrong variant"),
    }
}

#[test]
fn test_compute_seal_round_trip() {
    let request = Request::ComputeSeal {
        frame_id: frame(0x11),
        level: 4,
        data_digest: digest(0x22),
        auth: vec![0x33; 32],
    };

    let mut bytes = Vec::new(); ciborium::ser::into_writer(&request, &mut bytes).unwrap();
    let decoded: Request = ciborium::de::from_reader(&bytes[..]).unwrap();

    match decoded {
        Request::ComputeSeal {
            frame_id,
            level,
            data_digest,
            auth,
        } => {
            assert_eq!(frame_id, frame(0x11));
            assert_eq!(level, 4);
            assert_eq!(data_digest, digest(0x22));
            assert_eq!(auth, vec![0x33; 32]);
        }
        _ => panic!("Wrong variant"),
    }
}

#[test]
fn test_verify_seal_round_trip() {
    let request = Request::VerifySeal {
        frame_id: frame(0x44),
        level: 2,
        data_digest: digest(0x55),
        seal: digest(0x66),
        auth: vec![0x77; 32],
    };

    let mut bytes = Vec::new(); ciborium::ser::into_writer(&request, &mut bytes).unwrap();
    let decoded: Request = ciborium::de::from_reader(&bytes[..]).unwrap();

    match decoded {
        Request::VerifySeal {
            frame_id,
            level,
            data_digest,
            seal,
            auth,
        } => {
            assert_eq!(frame_id, frame(0x44));
            assert_eq!(level, 2);
            assert_eq!(data_digest, digest(0x55));
            assert_eq!(seal, digest(0x66));
            assert_eq!(auth, vec![0x77; 32]);
        }
        _ => panic!("Wrong variant"),
    }
}
