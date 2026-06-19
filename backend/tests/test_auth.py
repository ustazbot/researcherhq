import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.auth_service import (
    generate_password, hash_password, verify_password,
    create_jwt, decode_jwt
)

def test_generate_password_length():
    pwd = generate_password()
    assert len(pwd) == 8

def test_generate_password_alphanumeric():
    pwd = generate_password()
    assert pwd.isalnum()

def test_generate_password_unique():
    pwds = {generate_password() for _ in range(10)}
    assert len(pwds) > 1  # should not all be the same

def test_password_hash_verify():
    pwd = generate_password()
    hashed = hash_password(pwd)
    assert verify_password(pwd, hashed)

def test_password_wrong_rejected():
    pwd = generate_password()
    hashed = hash_password(pwd)
    assert not verify_password("wrongpass", hashed)

def test_jwt_roundtrip():
    token = create_jwt({"user_id": "abc123", "email": "test@test.com"})
    payload = decode_jwt(token)
    assert payload["user_id"] == "abc123"
    assert payload["email"] == "test@test.com"

def test_jwt_invalid_raises():
    try:
        decode_jwt("not.a.valid.token")
        assert False, "Should have raised"
    except ValueError:
        pass
