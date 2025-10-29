use elspeth_sidecar::protocol::Request;

#[test]
fn test_canonical_cbor_format() {
    let frame_id: [u8; 16] = [0x62, 0xab, 0x9b, 0x90, 0x25, 0xc1, 0x48, 0xd4, 0x9b, 0x4e, 0x9d, 0x36, 0x95, 0xd8, 0x6a, 0x72];
    let level: u32 = 2;
    let data_digest: [u8; 32] = [0xAA; 32];

    // Create Request and use canonical_bytes_without_auth()
    let request = Request::AuthorizeConstruct {
        frame_id,
        level,
        data_digest,
        auth: vec![],
    };

    let canonical_bytes = request.canonical_bytes_without_auth();

    // Convert to hex for comparison
    let hex_string: String = canonical_bytes.iter().map(|b| format!("{:02x}", b)).collect();

    println!("\nRust canonical CBOR (via Request::canonical_bytes_without_auth):");
    println!("  Hex: {}", hex_string);
    println!("  Length: {} bytes", canonical_bytes.len());

    // Python produces: 835062ab9b9025c148d49b4e9d3695d86a72025820aaaa...
    // Expected: 53 bytes
    println!("\nPython canonical CBOR:");
    println!("  Hex: 835062ab9b9025c148d49b4e9d3695d86a72025820aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    println!("  Length: 53 bytes");

    assert_eq!(canonical_bytes.len(), 53, "Canonical CBOR should be 53 bytes to match Python");
    assert_eq!(&hex_string[..10], "8350", "Should start with array(3) + bytes(16) markers");
}
