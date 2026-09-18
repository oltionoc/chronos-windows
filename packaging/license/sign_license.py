"""Mint a Chronos licence key. Run by the VENDOR only, with the private key.

    python sign_license.py --to "Client Name" --expires 2027-02-01

Prints one licence string. The client pastes it into Chronos under
Settings > Licence. Extending is just a newer --expires date and a new paste;
nothing is reinstalled.

Needs the private key file (chronos-license-key.json: {"n","e","d"} in hex),
kept OFF the repo and off any client machine. Point at it with --key or
CHRONOS_LICENSE_KEY, default ./chronos-license-key.json. Pure Python, no deps.
"""
import argparse
import base64
import hashlib
import json
import os
import sys
from datetime import date

_SHA256_DIGESTINFO = bytes.fromhex("3031300d060960864801650304020105000420")


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def sign(payload: bytes, n: int, d: int) -> bytes:
    k = (n.bit_length() + 7) // 8
    t = _SHA256_DIGESTINFO + hashlib.sha256(payload).digest()
    em = b"\x00\x01" + b"\xff" * (k - 3 - len(t)) + b"\x00" + t
    return pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")


def main() -> int:
    ap = argparse.ArgumentParser(description="Mint a Chronos licence key.")
    ap.add_argument("--to", required=True, help="who the licence is for (shown in the app)")
    ap.add_argument("--expires", required=True, help="last valid day, YYYY-MM-DD")
    ap.add_argument("--edition", default="standard")
    ap.add_argument("--id", default=None, help="licence id (default: <edition>-<expires>)")
    ap.add_argument("--key", default=os.environ.get("CHRONOS_LICENSE_KEY", "chronos-license-key.json"))
    args = ap.parse_args()

    try:
        expires = date.fromisoformat(args.expires)
    except ValueError:
        print("--expires must be YYYY-MM-DD", file=sys.stderr)
        return 2
    if expires < date.today():
        print(f"warning: {expires} is in the past; the key will already be expired.", file=sys.stderr)

    try:
        km = json.load(open(args.key))
        n, d = int(km["n"], 16), int(km["d"], 16)
    except (OSError, KeyError, ValueError) as exc:
        print(f"could not read private key from {args.key}: {exc}", file=sys.stderr)
        return 2

    payload = {
        "id": args.id or f"{args.edition}-{args.expires}",
        "issued_to": args.to,
        "edition": args.edition,
        "issued": date.today().isoformat(),
        "expires": args.expires,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    licence = _b64url(raw) + "." + _b64url(sign(raw, n, d))

    print(f"\nLicence for {args.to}, valid until {args.expires}:\n")
    print(licence)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
