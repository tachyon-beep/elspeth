from elspeth.core.security import generate_signature, verify_signature


def test_generate_and_verify_signature():
    data = b"payload"
    key = "secret"
    signature = generate_signature(data, key, algorithm="hmac-sha256")
    assert verify_signature(data, signature, key)
    assert not verify_signature(b"different", signature, key)
