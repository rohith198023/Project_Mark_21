import os
import hashlib
import secrets

# In a production local-first assistant, sensitive integrations (like API keys)
# must be encrypted before writing to disk (e.g. SQLite or Postgres).
# TODO: Integrate with OS keyring (e.g., keyring library or DBus/Keychain) where appropriate.

def get_encryption_key() -> bytes:
    """Retrieves or derives the local encryption key."""
    # Use a environment key, fallback to a derived key from static device identifier.
    key = os.getenv("JARVIS_ENCRYPTION_KEY")
    if not key:
        # Fallback key (for fallback/development only)
        key = "dev-fallback-key-should-be-replaced-in-prod"
    return hashlib.sha256(key.encode()).digest()

def encrypt_data(data: str) -> str:
    """Encrypts a string for safe storage in DB. Placeholder implementation."""
    # TODO: Implement Fernet (AES-128-CBC / HMAC) encryption using cryptography library.
    # Currently returns dummy prefixing to prove route works.
    return f"enc__{data}"

def decrypt_data(encrypted_data: str) -> str:
    """Decrypts a database string. Placeholder implementation."""
    # TODO: Implement symmetric decryption.
    if encrypted_data.startswith("enc__"):
        return encrypted_data[5:]
    return encrypted_data

def generate_local_token() -> str:
    """Generates a secure random token for IPC authentication."""
    return secrets.token_hex(32)

def verify_token(token: str, expected_token: str) -> bool:
    """Constant-time comparison for token security."""
    if not token or not expected_token:
        return False
    return secrets.compare_digest(token, expected_token)
