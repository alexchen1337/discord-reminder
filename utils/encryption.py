import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import config


def _get_fernet() -> Fernet:
    if not config.ENCRYPTION_KEY:
        raise ValueError("ENCRYPTION_KEY not set in environment")
    
    # derive a proper key from the config key
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"discord_reminder_salt",  # static salt, key should be unique
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(config.ENCRYPTION_KEY.encode()))
    return Fernet(key)


def encrypt_token(token: str) -> str:
    fernet = _get_fernet()
    return fernet.encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    fernet = _get_fernet()
    return fernet.decrypt(encrypted_token.encode()).decode()

