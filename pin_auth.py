"""PIN hashing and rate-limiting utilities."""
import hashlib, hmac, os, time
from collections import defaultdict

def hash_pin(pin: str) -> str:
    """Returns 'salthex:hashhex' using PBKDF2-HMAC-SHA256, 100k iterations."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'), salt, 100_000)
    return salt.hex() + ':' + dk.hex()

def verify_pin(pin: str, stored: str) -> bool:
    """Constant-time comparison."""
    try:
        salt_hex, hash_hex = stored.split(':', 1)
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac('sha256', pin.encode('utf-8'), salt, 100_000)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False

# In-memory per-IP rate limiter
_attempts: dict[str, list[float]] = defaultdict(list)
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60

def check_rate_limit(ip: str) -> tuple[bool, int]:
    """Returns (allowed, seconds_to_wait). Cleans up old entries."""
    now = time.time()
    _attempts[ip] = [t for t in _attempts[ip] if now - t < LOCKOUT_SECONDS]
    if len(_attempts[ip]) >= MAX_ATTEMPTS:
        wait = int(LOCKOUT_SECONDS - (now - _attempts[ip][0]))
        return False, max(wait, 1)
    return True, 0

def record_attempt(ip: str):
    _attempts[ip].append(time.time())

def clear_attempts(ip: str):
    _attempts.pop(ip, None)
