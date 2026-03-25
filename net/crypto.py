"""
Symmetric encryption for the transfer channel.
Uses AES-128-GCM via the `cryptography` library.

PSK-based: обидві сторони мають однаковий ключ у налаштуваннях.
Якщо PSK порожній — шифрування вимкнено.

Wire format per encrypted chunk:
  [4-byte nonce_len][nonce][4-byte ct_len][ciphertext+tag]
"""
import hashlib
import os
import struct

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _CRYPTO_AVAILABLE = True
except ImportError:
    _CRYPTO_AVAILABLE = False

# Precompiled struct — уникаємо повторного парсингу при кожному чанку
_UINT32 = struct.Struct(">I")
_NONCE_SIZE = 12  # AES-GCM стандартний nonce
# Prepack nonce_len — константа, не змінюється між чанками
_PACKED_NONCE_LEN = _UINT32.pack(_NONCE_SIZE)


def crypto_available() -> bool:
    return _CRYPTO_AVAILABLE


def derive_key(psk: str) -> bytes:
    """Derive a 16-byte AES key from PSK using SHA-256."""
    return hashlib.sha256(psk.encode("utf-8")).digest()[:16]


class ChannelCipher:
    """AES-128-GCM encrypt/decrypt per chunk."""

    def __init__(self, psk: str):
        if not _CRYPTO_AVAILABLE:
            raise RuntimeError(
                "Бібліотека 'cryptography' не встановлена. "
                "Запустіть: pip install cryptography"
            )
        self._aes = AESGCM(derive_key(psk))

    def encrypt(self, data: bytes) -> bytes:
        nonce = os.urandom(_NONCE_SIZE)
        ct = self._aes.encrypt(nonce, data, None)  # ct includes 16-byte GCM tag
        # Формат: [nonce_len(4)][nonce(12)][ct_len(4)][ct+tag]
        # _PACKED_NONCE_LEN — константа, не пакуємо щоразу
        return _PACKED_NONCE_LEN + nonce + _UINT32.pack(len(ct)) + ct

    def decrypt(self, data: bytes) -> bytes:
        offset = 0
        nonce_len = _UINT32.unpack_from(data, offset)[0]
        offset += 4
        nonce = data[offset: offset + nonce_len]
        offset += nonce_len
        ct_len = _UINT32.unpack_from(data, offset)[0]
        offset += 4
        ct = data[offset: offset + ct_len]
        return self._aes.decrypt(nonce, ct, None)
