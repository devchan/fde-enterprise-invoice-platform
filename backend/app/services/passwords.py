"""Password hashing and verification using PBKDF2-HMAC-SHA256.

Avoids a third-party dependency (bcrypt/argon2) by using the stdlib primitives;
the stored hash string is self-describing so parameters can evolve over time.
"""

import base64
import hashlib
import hmac
import secrets

# OWASP-recommended iteration count for PBKDF2-SHA256; stored in each hash so
# existing hashes keep verifying if this constant is later raised.
PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 390_000
SALT_BYTES = 16


class PasswordHashError(ValueError):
    pass


def hash_password(password: str) -> str:
    _validate_password(password)
    # Fresh random salt per password so identical passwords hash differently.
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _pbkdf2(password=password, salt=salt, iterations=PBKDF2_ITERATIONS)
    # Encode algorithm, iterations, salt and digest into one "$"-delimited,
    # self-describing string so verify_password can re-derive the hash without
    # any out-of-band parameter storage.
    return "$".join(
        [
            PBKDF2_ALGORITHM,
            str(PBKDF2_ITERATIONS),
            _b64(salt),
            _b64(digest),
        ]
    )


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False

    try:
        algorithm, iterations_raw, salt_raw, digest_raw = password_hash.split("$", 3)
        if algorithm != PBKDF2_ALGORITHM:
            return False
        iterations = int(iterations_raw)
        salt = _unb64(salt_raw)
        expected_digest = _unb64(digest_raw)
    except (ValueError, TypeError):
        return False

    # Re-derive using the iteration count stored in the hash (not the current
    # constant) so older hashes still verify after the constant is raised.
    supplied_digest = _pbkdf2(password=password, salt=salt, iterations=iterations)
    # Constant-time comparison to avoid leaking digest bytes via timing.
    return hmac.compare_digest(supplied_digest, expected_digest)


def _validate_password(password: str) -> None:
    if len(password) < 12:
        raise PasswordHashError("Password must be at least 12 characters.")


def _pbkdf2(*, password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
