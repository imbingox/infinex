import hashlib
import secrets


def generate_worker_token() -> str:
    return secrets.token_urlsafe(32)


def hash_worker_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_worker_token(token: str, credential_hash: str | None) -> bool:
    if not credential_hash:
        return False
    return secrets.compare_digest(hash_worker_token(token), credential_hash)
