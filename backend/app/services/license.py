"""Licence gating.

A licence is a signed statement of who the software is for and when it stops
working. Signing is RSA-2048 / PKCS#1 v1.5 / SHA-256; the app holds only the
PUBLIC key and only ever VERIFIES — it cannot mint a licence, so nobody on the
client's machine can extend their own. Signing is done off-site with the
private key (packaging/license/sign_license.py).

Verification is pure Python (`pow()` + `hashlib`) on purpose: no third-party
crypto library, so nothing extra to compile into the Windows build, and the
whole check is auditable in one screen.

Licence string: `<payload>.<signature>`, both URL-safe base64 (no padding).
Payload is compact JSON with sorted keys:
    {"id","issued_to","edition","issued":"YYYY-MM-DD","expires":"YYYY-MM-DD"}

Effective licence = the pasted key from the database if it verifies, otherwise
the built-in default below. So a fresh install works out of the box and stops
on the default's expiry; pasting a newer signed key extends it with no
reinstall. The worker never calls any of this, so punches keep being collected
after expiry — only the user-facing API is gated (see app/main.py).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone

# Public key (RSA-2048). The matching private key is held off-site and is not
# in this repository.
_N = int(
    "0xb202718729eb54c36b27dbe2b2df3efc8c2a9d6eb1990af727d8557e74b514aa"
    "c49c51cc4fb6e7d9c945f7da1432461171883a996d337bf84125937a4f14539b02"
    "12896a3db400a58b037efec83d057001d9dd69fd73a387c5637dd574c6126534f4"
    "73040713d0dd220424ce99f0518299bdf60affaa452ba4faf69a36b52052a61cbf"
    "f04850f7ffe8f2ed086dd38c04c332a00257de401020e7bb9675c53c8574b25a33"
    "68960841a80c735b44daddb8f016b29fd2dbae11261b1de635d13da30c3b455a66"
    "f4502a658eaa1d19423dffd43a436a398cbe1dae0440bed6c40ef9453df23aabde"
    "5c1a6f1d23f79742cd93d0bf5e53e555e71a55f478e11821179f",
    16,
)
_E = 65537

# Ships enabled and expiring, so an install with no key of its own still
# stops on the agreed date. Replaced at runtime by any newer signed key.
DEFAULT_LICENSE = (
    "eyJlZGl0aW9uIjoiYmV0YSIsImV4cGlyZXMiOiIyMDI2LTExLTEwIiwiaWQiOiJiZXRhLTAwMDEiLCJpc3N1ZWQiOiIyMDI2"
    "LTA5LTE4IiwiaXNzdWVkX3RvIjoiQmV0YSJ9.B2VM80FHHlD-LvjRPlajgpiGPLnO_TWzh9dIZsfyTZP7oVDSK-Kvu8Bb_lO"
    "Bs73KVYoXGZ4dNa7J3p4vmMrZAICaqLAYGldowzUIp78zNgQFmCDz8Lj6i_gb-5v8-J1xsjKutuJ3osOfPIRGV1dQuMifri"
    "PtA4Jm59HMYW9zCMOqS3G2Gm3u1DOP-8-qoPtCV2sthKWtju5nEeoc3Kcrgi9vyDgIe7DdivuzAuSHoLr_OOpYlaEMcIm6w"
    "I6hNmgrJi-UJauRbmUrduGQGg3zaJbjNFj3Rama5Tr3Vv5KnlUanawds1wIKXiB5Cj8E4X1FQKVfjB-iRJjQLmZneh34Q"
)

# How many days before expiry the app starts warning.
WARN_WITHIN_DAYS = 14

# SHA-256 DigestInfo prefix (RFC 8017), the T in a PKCS#1 v1.5 signature.
_SHA256_DIGESTINFO = bytes.fromhex("3031300d060960864801650304020105000420")


class LicenseError(Exception):
    """A licence string is malformed or its signature does not verify."""


def _b64url_decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _rsa_pkcs1_verify(message: bytes, signature: bytes) -> bool:
    """True when `signature` is a valid RSA PKCS#1 v1.5 SHA-256 signature of
    `message` under the embedded public key. Verification only."""
    k = (_N.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    s = int.from_bytes(signature, "big")
    if s >= _N:
        return False
    em = pow(s, _E, _N).to_bytes(k, "big")
    t = _SHA256_DIGESTINFO + hashlib.sha256(message).digest()
    expected = b"\x00\x01" + b"\xff" * (k - 3 - len(t)) + b"\x00" + t
    # Constant-time: this is a signature check.
    return hmac.compare_digest(em, expected)


@dataclass(frozen=True)
class License:
    id: str
    issued_to: str
    edition: str
    issued: date
    expires: date

    def days_left(self, today: date | None = None) -> int:
        return (self.expires - (today or _today())).days

    def is_expired(self, today: date | None = None) -> bool:
        return self.days_left(today) < 0


def _today() -> date:
    return datetime.now(timezone.utc).date()


def parse_license(license_str: str) -> License:
    """Verify a licence string and return it, or raise LicenseError."""
    try:
        payload_b64, sig_b64 = license_str.strip().split(".", 1)
        payload = _b64url_decode(payload_b64)
        signature = _b64url_decode(sig_b64)
    except (ValueError, binascii.Error) as exc:
        raise LicenseError("Licence key is not in the expected format") from exc

    if not _rsa_pkcs1_verify(payload, signature):
        raise LicenseError("Licence key signature is not valid")

    try:
        data = json.loads(payload)
        return License(
            id=str(data["id"]),
            issued_to=str(data["issued_to"]),
            edition=str(data["edition"]),
            issued=date.fromisoformat(data["issued"]),
            expires=date.fromisoformat(data["expires"]),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise LicenseError("Licence key contents are invalid") from exc


def effective_license(stored_key: str | None) -> License:
    """The licence in force: the stored (pasted) key if it verifies AND lasts
    at least as long as the default, otherwise the built-in default.

    The "at least as long" rule stops a valid but OLDER key (e.g. a copy of the
    original beta key pasted back in) from ever shortening the term below what
    shipped."""
    default = parse_license(DEFAULT_LICENSE)
    if stored_key:
        try:
            pasted = parse_license(stored_key)
        except LicenseError:
            return default
        if pasted.expires >= default.expires:
            return pasted
    return default


def license_status(stored_key: str | None, today: date | None = None) -> dict:
    """Serialisable status for the API and the frontend banner."""
    lic = effective_license(stored_key)
    today = today or _today()
    days = lic.days_left(today)
    return {
        "issued_to": lic.issued_to,
        "edition": lic.edition,
        "expires": lic.expires.isoformat(),
        "days_left": days,
        "expired": days < 0,
        "expiring_soon": 0 <= days <= WARN_WITHIN_DAYS,
    }
